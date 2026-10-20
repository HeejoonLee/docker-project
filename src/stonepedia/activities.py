"""Activities: everything that touches the filesystem, git, the agent, or other workflows.

Article paths in ArticleChange are relative to the Bundle root; repo paths are root/path.
"""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError

from stonepedia import appconfig, bundle, frontmatter, git, maintenance, sources
from stonepedia.agent import TASK_DIR, AgentConfigError, AgentError, claude, fake, prompt
from stonepedia.bundle import BundleSettings, Template
from stonepedia.config import Settings
from stonepedia.models import (
    AgentCheck,
    AgentJob,
    AgentOutcome,
    ArticleChange,
    BundleInit,
    BundleSpec,
    ChangedLink,
    Finding,
    CommitRequest,
    CommitResult,
    ProposalInput,
    SourceInfo,
    SourceInput,
)


def change_id(path: str) -> str:
    return "c" + hashlib.sha1(path.encode()).hexdigest()[:10]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _in_root(root: str, path: str) -> str:
    return path if root == "." else f"{root}/{path}"


class Activities:
    def __init__(self, settings: Settings, client: Client | None = None):
        self.settings = settings
        self.client = client

    def _repo(self, slug: str) -> Path:
        return self.settings.bundles_dir / slug

    async def _spec(self, slug: str) -> BundleSpec:
        from stonepedia.workflows import BundleWorkflow  # avoid import cycle

        assert self.client is not None
        spec = await self.client.get_workflow_handle(f"bundle-{slug}").query(BundleWorkflow.info)
        if spec is None:
            raise ApplicationError(f"Bundle '{slug}' is not ready", non_retryable=True)
        return spec

    # ---------- Bundles ----------

    @activity.defn
    def init_bundle(self, spec: BundleSpec) -> BundleInit:
        """Create a Bundle repo, or clone an existing one and set it up for Stonepedia."""
        repo = self._repo(spec.slug)
        if (repo / ".git").exists() and (repo / spec.root / ".stonepedia" / "bundle.yaml").exists():
            return BundleInit(head=git.head(repo), branch=git.current_branch(repo))  # retry after success
        if repo.exists():
            shutil.rmtree(repo)  # leftovers of a failed attempt
        try:
            if spec.clone_url:
                git.clone(spec.clone_url, repo, spec.branch if spec.branch != "main" else "")
            else:
                git.init(repo)
        except git.GitError as err:
            shutil.rmtree(repo, ignore_errors=True)
            raise ApplicationError(str(err), non_retryable=True) from err
        root = repo / spec.root
        if spec.clone_url and not root.is_dir():
            shutil.rmtree(repo, ignore_errors=True)
            raise ApplicationError(f"The folder '{spec.root}' does not exist in that repository.", non_retryable=True)
        root.mkdir(parents=True, exist_ok=True)

        imported = spec.clone_url != ""
        settings = BundleSettings(
            name=spec.name,
            language=spec.language,
            id_prefix=spec.id_prefix,
            generate_index=not (imported and (root / "index.md").exists()),
            generate_manifest=not (imported and (root / "manifest.json").exists()),
        )
        bundle.save_settings(root, settings)
        if not (bundle.meta_dir(root) / "template.yaml").exists():
            template = bundle.infer_template(root) if imported and bundle.articles(root) else bundle.load_template(root)
            bundle.save_template(root, template)
        bundle.regenerate(root, settings)
        git.set_remote(repo, spec.remote_url or spec.clone_url)
        message = "Set up Stonepedia" if imported else f"Create bundle {spec.name}"
        head = git.commit_all(repo, message, git.SYSTEM_AUTHOR)
        return BundleInit(head=head, branch=git.current_branch(repo))

    @activity.defn
    def save_bundle_config(
        self, spec: BundleSpec, settings: BundleSettings | None, template: Template | None, editor: str
    ) -> str | None:
        """Write Bundle settings and/or Template into the repo as one commit by `editor`."""
        repo = self._repo(spec.slug)
        root = repo / spec.root
        changed = []
        if settings is not None:
            bundle.save_settings(root, settings)
            changed.append("settings")
            bundle.regenerate(root, settings)
        if template is not None:
            bundle.save_template(root, template)
            changed.append("template")
        if git.is_clean(repo):
            return None
        author = (editor, f"{_email_local(editor)}@stonepedia.local")
        return git.commit_all(repo, f"Update Bundle {' and '.join(changed)}", author)

    @activity.defn
    def set_remote(self, spec: BundleSpec) -> None:
        git.set_remote(self._repo(spec.slug), spec.remote_url)

    @activity.defn
    def sync_bundle(self, spec: BundleSpec) -> None:
        """Bring in commits from the remote (rebasing unpushed local commits on top)."""
        try:
            git.sync(self._repo(spec.slug), spec.branch)
        except git.GitError as err:
            raise ApplicationError(str(err), non_retryable=True) from err

    @activity.defn
    def push_bundle(self, spec: BundleSpec) -> None:
        repo = self._repo(spec.slug)
        try:
            git.sync(repo, spec.branch)
            git.push(repo, spec.branch)
        except git.GitError as err:
            conflict = "conflict" in str(err).lower()
            raise ApplicationError(str(err), type="Conflict" if conflict else "PushFailed", non_retryable=conflict) from err

    # ---------- Sources ----------

    @activity.defn
    def prepare_source(self, inp: ProposalInput) -> SourceInfo:
        """Extract the submitted Source into <data>/sources/<proposal id>/."""
        dest = self.settings.sources_dir / inp.proposal_id
        meta = dest / "meta.yaml"
        if meta.exists():  # activity retry after success
            return _with_preview(SourceInfo.model_validate(yaml.safe_load(meta.read_text())), dest)
        shutil.rmtree(dest, ignore_errors=True)
        cfg = appconfig.load(self.settings.config_dir)
        upload = None
        if inp.source.kind == "file":
            staged = self.settings.uploads_dir / inp.proposal_id
            files = sorted(staged.iterdir()) if staged.exists() else []
            upload = files[0] if files else None
        try:
            info = sources.prepare(
                inp.source,
                upload,
                dest,
                submitted_by=inp.submitted_by,
                title=inp.title,
                max_bytes=cfg.max_source_mb * 2**20,
                verify_tls=cfg.verify_link_certificates,
            )
        except sources.SourceError as err:
            shutil.rmtree(dest, ignore_errors=True)
            raise ApplicationError(str(err), non_retryable=True) from err
        shutil.rmtree(self.settings.uploads_dir / inp.proposal_id, ignore_errors=True)
        return _with_preview(info, dest)

    # ---------- Agent ----------

    @activity.defn
    async def run_agent(self, job: AgentJob) -> AgentOutcome:
        """Run the agent in a scratch worktree of the Bundle and return its edits as Article changes."""
        repo = self._repo(job.bundle)
        if not (repo / ".git").exists():
            raise ApplicationError(f"No Bundle repo for '{job.bundle}'", non_retryable=True)
        job.root = (await self._spec(job.bundle)).root
        cfg = appconfig.load(self.settings.config_dir)
        workspace = self.settings.scratch_dir / f"{job.proposal_id}-{job.attempt_key or 'run'}-{activity.info().attempt}"
        ws_root = workspace / job.root
        await asyncio.to_thread(_fresh_worktree, repo, workspace)
        try:
            staged = self.settings.sources_dir / job.source.id
            stale_targets = await asyncio.to_thread(_prepare_workspace, ws_root, job, staged)
            if cfg.agent == "fake":
                summary, cost, agent_name = fake.run(ws_root, job), None, "fake-agent"
            else:
                settings = bundle.load_settings(ws_root)
                template = bundle.load_template(ws_root)
                text = prompt.build(job, settings.model_dump(), template.model_dump(), stale_targets)
                summary, cost = await claude.run(
                    ws_root,
                    text,
                    self._claude_settings_file(),
                    timeout_s=cfg.agent_timeout_minutes * 60,
                    heartbeat=activity.heartbeat,
                )
                agent_name = "claude-code"
            changes = await asyncio.to_thread(_collect_changes, workspace, job, agent_name)
            return AgentOutcome(changes=changes, summary=summary, agent=agent_name, cost_usd=cost)
        except AgentConfigError as err:
            raise ApplicationError(str(err), non_retryable=True) from err
        except AgentError as err:
            raise ApplicationError(str(err)) from err
        finally:
            await asyncio.to_thread(_remove_worktree, repo, workspace)

    @activity.defn
    async def check_agent(self) -> AgentCheck:
        """Ask the configured agent for a trivial reply, to test the Settings page configuration."""
        cfg = appconfig.load(self.settings.config_dir)
        started = time.monotonic()
        if cfg.agent == "fake":
            return AgentCheck(ok=True, message="The fake agent is selected; nothing to test.", agent="fake", seconds=0)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                reply, _ = await claude.run(
                    Path(tmp),
                    "Reply with exactly the word OK and nothing else.",
                    self._claude_settings_file(),
                    timeout_s=180,
                    heartbeat=activity.heartbeat,
                )
                ok = "OK" in reply.upper()
                message = reply if ok else f"Unexpected reply: {reply}"
            except (AgentError, AgentConfigError) as err:
                ok, message = False, str(err)
        return AgentCheck(ok=ok, message=message, agent=cfg.agent, seconds=round(time.monotonic() - started, 1))

    def _claude_settings_file(self) -> Path:
        path = appconfig.claude_settings_path(self.settings.config_dir)
        if not path.exists():
            appconfig.save_claude_settings(self.settings.config_dir, "{}\n")
        return path

    @activity.defn
    async def refresh_base(self, bundle_slug: str, path: str) -> ArticleChange:
        """Current state of an Article at the Bundle's HEAD (used when a reviewer edits a stale change)."""
        repo = self._repo(bundle_slug)
        repo_path = _in_root((await self._spec(bundle_slug)).root, path)
        blob = git.blob(repo, repo_path)
        return ArticleChange(
            id=change_id(path),
            path=path,
            kind="update" if blob else "create",
            base_blob=blob,
            base_content=git.show(repo, repo_path) if blob else None,
            content="",
        )

    # ---------- Commits ----------

    @activity.defn
    def commit_changes(self, spec: BundleSpec, req: CommitRequest) -> CommitResult:
        """Write accepted changes into the Bundle repo as one commit, unless any is stale."""
        repo = self._repo(spec.slug)
        root = repo / spec.root
        if not git.is_clean(repo):
            raise ApplicationError(
                f"Bundle {spec.slug} has uncommitted local changes; resolve them on the server first",
                non_retryable=True,
            )
        stale = [c.id for c in req.changes if git.blob(repo, _in_root(spec.root, c.path)) != c.base_blob]
        if stale:
            return CommitResult(stale_ids=stale)
        now = _now()
        if req.source_id:
            staged = self.settings.sources_dir / req.source_id
            if staged.exists() and not (root / "sources" / req.source_id).exists():
                shutil.copytree(staged, root / "sources" / req.source_id)
        for change in req.changes:
            target = root / change.path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = frontmatter.update(
                change.content,
                status="retired" if change.kind == "retire" else "accepted",
                review={"state": "accepted", "reviewer": req.reviewer, "reviewed_at": now},
            )
            target.write_text(content)
        settings = bundle.load_settings(root)
        ids = bundle.assign_ids(root, settings, [c.path for c in req.changes if c.kind == "create"])
        bundle.regenerate(root, settings)

        message = f"{req.title}\n\nProposal: {req.proposal_id}\nReviewed-by: {req.reviewer}\n"
        if req.source_id:
            message += f"Source: sources/{req.source_id}/\n"
        for change in req.changes:
            extra = f" (edited by {change.edited_by})" if change.edited_by else ""
            new_id = f" [{ids[change.path]}]" if change.path in ids else ""
            message += f"\n- {change.kind}: {change.path}{new_id}{extra}"
        author = (req.reviewer, f"{_email_local(req.reviewer)}@stonepedia.local")
        return CommitResult(commit=git.commit_all(repo, message, author))

    @activity.defn
    async def commit_via_bundle(self, bundle_slug: str, req: CommitRequest) -> CommitResult:
        """Hand the commit to the Bundle's workflow, which serializes all git writes."""
        from stonepedia.workflows import BundleWorkflow  # avoid import cycle

        assert self.client is not None
        handle = self.client.get_workflow_handle(f"bundle-{bundle_slug}")
        return await handle.execute_update(BundleWorkflow.commit, req)

    # ---------- Maintenance ----------

    @activity.defn
    async def integrity_check(self, bundle_slug: str) -> list[Finding]:
        spec = await self._spec(bundle_slug)
        repo = self._repo(bundle_slug)
        return await asyncio.to_thread(maintenance.check, repo / spec.root, repo)

    @activity.defn
    async def find_changed_links(self, bundle_slug: str) -> list[ChangedLink]:
        """Re-fetch every cited link Source; return those whose text changed since last seen."""
        spec = await self._spec(bundle_slug)
        root = self._repo(bundle_slug) / spec.root
        cfg = appconfig.load(self.settings.config_dir)
        seen_file = self.settings.data_dir / "maintenance" / bundle_slug / "links.json"
        seen: dict[str, str] = json.loads(seen_file.read_text()) if seen_file.exists() else {}

        cited_by: dict[str, list[str]] = {}
        for rel, meta in bundle.articles(root):
            if meta.get("status") == "retired":
                continue
            for src in meta.get("sources") or []:
                if isinstance(src, dict) and src.get("id"):
                    cited_by.setdefault(str(src["id"]), []).append(rel)

        newest: dict[str, tuple[str, dict]] = {}  # url -> (source id, meta) of the latest capture
        for meta_file in sorted((root / "sources").glob("*/meta.yaml")) if (root / "sources").is_dir() else []:
            meta = yaml.safe_load(meta_file.read_text()) or {}
            sid = meta_file.parent.name
            if meta.get("kind") != "link" or sid not in cited_by:
                continue
            url = meta.get("url", "")
            if url not in newest or meta.get("submitted_at", "") > newest[url][1].get("submitted_at", ""):
                newest[url] = (sid, meta)

        changed = []
        for url, (sid, meta) in newest.items():
            activity.heartbeat(url)
            old_text = (root / "sources" / sid / "text.md").read_text(errors="replace")
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    await asyncio.to_thread(
                        sources.prepare, SourceInput(kind="link", url=url), None, Path(tmp) / "s", "maintenance",
                        "", cfg.max_source_mb * 2**20, cfg.verify_link_certificates,
                    )
                    new_text = (Path(tmp) / "s" / "text.md").read_text(errors="replace")
                except sources.SourceError as err:
                    changed.append(ChangedLink(source_id=sid, url=url, title=meta.get("title", url),
                                               cited_by=cited_by[sid], error=str(err)))
                    continue
            digest = hashlib.sha256(new_text.encode()).hexdigest()
            if new_text.strip() == old_text.strip() or seen.get(url) == digest:
                continue
            seen[url] = digest
            changed.append(ChangedLink(source_id=sid, url=url, title=meta.get("title", url), cited_by=cited_by[sid]))
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        seen_file.write_text(json.dumps(seen, indent=2))
        return changed

    def all(self) -> list:
        return [
            self.init_bundle,
            self.save_bundle_config,
            self.set_remote,
            self.sync_bundle,
            self.push_bundle,
            self.prepare_source,
            self.run_agent,
            self.check_agent,
            self.refresh_base,
            self.commit_changes,
            self.commit_via_bundle,
            self.integrity_check,
            self.find_changed_links,
        ]


# ---------- Workspace helpers ----------


def _fresh_worktree(repo: Path, workspace: Path) -> None:
    if workspace.exists():
        _remove_worktree(repo, workspace)
    git.worktree_add(repo, workspace)


def _remove_worktree(repo: Path, workspace: Path) -> None:
    git.worktree_remove(repo, workspace)
    shutil.rmtree(workspace, ignore_errors=True)


def _prepare_workspace(ws_root: Path, job: AgentJob, staged_source: Path) -> list[str]:
    """Place the Source and this Proposal's current changes into the workspace.

    A carried change whose Article moved on since it was proposed is not written over the newer
    version; it goes to the task folder instead. Returns those stale paths among the targets.
    """
    if staged_source.exists():
        dest = ws_root / "sources" / job.source.id
        if not dest.exists():
            shutil.copytree(staged_source, dest)
    task = ws_root / TASK_DIR
    task.mkdir(parents=True, exist_ok=True)
    stale_targets = []
    for change in job.carried:
        dest = ws_root / change.path
        if git.blob(ws_root, _in_root(job.root, change.path)) != change.base_blob:  # HEAD:<path> is repo-relative
            previous = task / "previous" / change.path
            previous.parent.mkdir(parents=True, exist_ok=True)
            previous.write_text(change.content)
            if change.path in job.targets:
                stale_targets.append(change.path)
            continue
        if change.kind == "retire":
            dest.unlink(missing_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(change.content)
    return stale_targets


def source_entry(info: SourceInfo, article_path: str) -> dict:
    """The `sources` frontmatter entry citing a Source from an Article."""
    rel = lambda name: os.path.relpath(f"sources/{info.id}/{name}", os.path.dirname(article_path) or ".")  # noqa: E731
    entry: dict = {"id": info.id, "title": info.title}
    if info.kind == "link":
        entry["resource"] = info.url
        entry["archived"] = rel("text.md")
    else:
        entry["resource"] = rel(info.original)
    if info.kind in ("text", "request"):
        entry["author"] = f"human:{info.submitted_by}"
    return entry


def _with_preview(info: SourceInfo, folder: Path) -> SourceInfo:
    text = (folder / "text.md").read_text() if (folder / "text.md").exists() else ""
    info.preview = text[:4000]
    return info


def _collect_changes(workspace: Path, job: AgentJob, agent_name: str) -> list[ArticleChange]:
    """Article changes in the workspace relative to HEAD: edits, new files, and deletions (= retire)."""
    generated = {"by": agent_name, "at": _now()}
    carried = {c.path: c.content for c in job.carried}
    prefix = "" if job.root == "." else job.root + "/"
    changes = []

    def rel_paths(paths: list[str]) -> list[str]:
        return [p[len(prefix):] for p in paths if p.startswith(prefix) and bundle.is_article(p[len(prefix):])]

    for path in rel_paths(git.changed_paths(workspace)):
        repo_path = prefix + path
        base_blob = git.blob(workspace, repo_path)
        base_content = git.show(workspace, repo_path) if base_blob else None
        written = (workspace / repo_path).read_text()
        if carried.get(path) == written:
            content = written  # carried over and left untouched by the agent
        else:
            cite = None if job.source.kind == "audit" else source_entry(job.source, path)
            content = frontmatter.finalize(written, base_content, generated, cite)
        meta, _ = frontmatter.split(content)
        changes.append(ArticleChange(
            id=change_id(path),
            path=path,
            kind="update" if base_blob else "create",
            base_blob=base_blob,
            base_content=base_content,
            content=content,
            title=str(meta.get("title", path)),
        ))

    for path in rel_paths(git.deleted_paths(workspace)):
        repo_path = prefix + path
        base_content = git.show(workspace, repo_path) or ""
        meta, _ = frontmatter.split(base_content)
        changes.append(ArticleChange(
            id=change_id(path),
            path=path,
            kind="retire",
            base_blob=git.blob(workspace, repo_path),
            base_content=base_content,
            content=frontmatter.update(base_content, status="retired"),
            title=str(meta.get("title", path)),
        ))
    return changes


def _email_local(name: str) -> str:
    local = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in name.lower()).strip("-")
    return local or "reviewer"
