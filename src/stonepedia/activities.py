"""Activities: everything that touches the filesystem, git, the agent, or other workflows."""

import asyncio
import hashlib
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

from stonepedia import appconfig, frontmatter, git, sources
from stonepedia.agent import TASK_DIR, AgentConfigError, AgentError, claude, fake, prompt
from stonepedia.config import Settings
from stonepedia.models import (
    AgentCheck,
    AgentJob,
    AgentOutcome,
    ArticleChange,
    BundleSpec,
    CommitRequest,
    CommitResult,
    ProposalInput,
    SourceInfo,
)
from stonepedia.template import DEFAULT_TEMPLATE

# Files in a Bundle that are never Articles.
_NOT_ARTICLES = ("index.md", "README.md")
_SYSTEM_DIRS = (".stonepedia/", "sources/")


def change_id(path: str) -> str:
    return "c" + hashlib.sha1(path.encode()).hexdigest()[:10]


def is_article(path: str) -> bool:
    return path.endswith(".md") and path not in _NOT_ARTICLES and not path.startswith(_SYSTEM_DIRS)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Activities:
    def __init__(self, settings: Settings, client: Client | None = None):
        self.settings = settings
        self.client = client

    def _repo(self, slug: str) -> Path:
        return self.settings.bundles_dir / slug

    # ---------- Bundles ----------

    @activity.defn
    def init_bundle(self, spec: BundleSpec) -> str:
        repo = self._repo(spec.slug)
        if repo.exists() and any(repo.iterdir()):
            if (repo / ".git").exists() and (repo / ".stonepedia" / "bundle.yaml").exists():
                return git.head(repo)  # already initialized (activity retry)
            raise ApplicationError(f"{repo} already exists and is not empty", non_retryable=True)
        git.init(repo)
        meta = repo / ".stonepedia"
        meta.mkdir()
        bundle = {"name": spec.name, "language": spec.language, "id_prefix": spec.id_prefix}
        (meta / "bundle.yaml").write_text(yaml.safe_dump(bundle, sort_keys=False, allow_unicode=True))
        (meta / "template.yaml").write_text(
            yaml.safe_dump(DEFAULT_TEMPLATE, sort_keys=False, allow_unicode=True, width=1000)
        )
        (repo / "index.md").write_text(f'---\nokf_version: "0.2"\n---\n\n# {spec.name}\n')
        return git.commit_all(repo, f"Create bundle {spec.name}", git.SYSTEM_AUTHOR)

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
        cfg = appconfig.load(self.settings.config_dir)
        workspace = self.settings.scratch_dir / f"{job.proposal_id}-{job.attempt_key or 'run'}-{activity.info().attempt}"
        await asyncio.to_thread(_fresh_worktree, repo, workspace)
        try:
            staged = self.settings.sources_dir / job.source.id
            stale_targets = await asyncio.to_thread(_prepare_workspace, workspace, job, staged)
            if cfg.agent == "fake":
                summary, cost, agent_name = fake.run(workspace, job), None, "fake-agent"
                if job.source.kind == "file" and job.source.media == "image":
                    summary += " (the fake agent cannot read images)"
            else:
                bundle = yaml.safe_load((workspace / ".stonepedia" / "bundle.yaml").read_text()) or {}
                template = yaml.safe_load((workspace / ".stonepedia" / "template.yaml").read_text()) or {}
                text = prompt.build(job, bundle, template, stale_targets)
                summary, cost = await claude.run(
                    workspace,
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
    def refresh_base(self, bundle: str, path: str) -> ArticleChange:
        """Current state of an Article at the Bundle's HEAD (used when a reviewer edits a stale change)."""
        repo = self._repo(bundle)
        blob = git.blob(repo, path)
        return ArticleChange(
            id=change_id(path),
            path=path,
            kind="update" if blob else "create",
            base_blob=blob,
            base_content=git.show(repo, path) if blob else None,
            content="",
        )

    # ---------- Commits ----------

    @activity.defn
    def commit_changes(self, bundle: str, req: CommitRequest) -> CommitResult:
        """Write accepted changes into the Bundle repo as one commit, unless any is stale."""
        repo = self._repo(bundle)
        if not git.is_clean(repo):
            raise ApplicationError(
                f"Bundle {bundle} has uncommitted local changes; resolve them on the server first",
                non_retryable=True,
            )
        stale = [c.id for c in req.changes if git.blob(repo, c.path) != c.base_blob]
        if stale:
            return CommitResult(stale_ids=stale)
        now = _now()
        if req.source_id:
            staged = self.settings.sources_dir / req.source_id
            if staged.exists() and not (repo / "sources" / req.source_id).exists():
                shutil.copytree(staged, repo / "sources" / req.source_id)
        for change in req.changes:
            target = repo / change.path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = frontmatter.update(
                change.content,
                status="retired" if change.kind == "retire" else "accepted",
                review={"state": "accepted", "reviewer": req.reviewer, "reviewed_at": now},
            )
            target.write_text(content)
        message = f"{req.title}\n\nProposal: {req.proposal_id}\nReviewed-by: {req.reviewer}\n"
        if req.source_id:
            message += f"Source: sources/{req.source_id}/\n"
        for change in req.changes:
            extra = f" (edited by {change.edited_by})" if change.edited_by else ""
            message += f"\n- {change.kind}: {change.path}{extra}"
        author = (req.reviewer, f"{_email_local(req.reviewer)}@stonepedia.local")
        return CommitResult(commit=git.commit_all(repo, message, author))

    @activity.defn
    async def commit_via_bundle(self, bundle: str, req: CommitRequest) -> CommitResult:
        """Hand the commit to the Bundle's workflow, which serializes all git writes."""
        from stonepedia.workflows import BundleWorkflow  # avoid import cycle

        assert self.client is not None
        handle = self.client.get_workflow_handle(f"bundle-{bundle}")
        return await handle.execute_update(BundleWorkflow.commit, req)

    def all(self) -> list:
        return [
            self.init_bundle,
            self.prepare_source,
            self.run_agent,
            self.check_agent,
            self.refresh_base,
            self.commit_changes,
            self.commit_via_bundle,
        ]


# ---------- Workspace helpers ----------


def _fresh_worktree(repo: Path, workspace: Path) -> None:
    if workspace.exists():
        _remove_worktree(repo, workspace)
    git.worktree_add(repo, workspace)


def _remove_worktree(repo: Path, workspace: Path) -> None:
    git.worktree_remove(repo, workspace)
    shutil.rmtree(workspace, ignore_errors=True)


def _prepare_workspace(workspace: Path, job: AgentJob, staged_source: Path) -> list[str]:
    """Place the Source and this Proposal's current changes into the workspace.

    A carried change whose Article moved on since it was proposed is not written over the newer
    version; it goes to the task folder instead. Returns those stale paths among the targets.
    """
    if staged_source.exists():
        dest = workspace / "sources" / job.source.id
        if not dest.exists():
            shutil.copytree(staged_source, dest)
    task = workspace / TASK_DIR
    task.mkdir(parents=True, exist_ok=True)
    stale_targets = []
    for change in job.carried:
        dest = workspace / change.path
        if git.blob(workspace, change.path) != change.base_blob:
            previous = task / "previous" / change.path
            previous.parent.mkdir(parents=True, exist_ok=True)
            previous.write_text(change.content)
            if change.path in job.targets:
                stale_targets.append(change.path)
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
    generated = {"by": agent_name, "at": _now()}
    carried = {c.path: c.content for c in job.carried}
    changes = []
    for path in git.changed_paths(workspace):
        if not is_article(path):
            continue
        base_blob = git.blob(workspace, path)
        base_content = git.show(workspace, path) if base_blob else None
        written = (workspace / path).read_text()
        if carried.get(path) == written:
            content = written  # carried over and left untouched by the agent
        else:
            content = frontmatter.finalize(written, base_content, generated, source_entry(job.source, path))
        meta, _ = frontmatter.split(content)
        changes.append(
            ArticleChange(
                id=change_id(path),
                path=path,
                kind="update" if base_blob else "create",
                base_blob=base_blob,
                base_content=base_content,
                content=content,
                title=str(meta.get("title", path)),
            )
        )
    return changes


def _email_local(name: str) -> str:
    local = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in name.lower()).strip("-")
    return local or "reviewer"
