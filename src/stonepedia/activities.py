"""Activities: everything that touches the filesystem, git, the agent, or other workflows."""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError

from stonepedia import frontmatter, git
from stonepedia.agent import fake
from stonepedia.config import Settings
from stonepedia.models import AgentTask, ArticleChange, BundleSpec, CommitRequest, CommitResult
from stonepedia.template import DEFAULT_TEMPLATE

# Files in a Bundle that are never Articles.
_NOT_ARTICLES = ("index.md", "README.md")
_SYSTEM_DIRS = (".stonepedia/", "sources/")


def _change_id(path: str) -> str:
    return "c" + hashlib.sha1(path.encode()).hexdigest()[:10]


def _is_article(path: str) -> bool:
    return path.endswith(".md") and path not in _NOT_ARTICLES and not path.startswith(_SYSTEM_DIRS)


class Activities:
    def __init__(self, settings: Settings, client: Client | None = None):
        self.settings = settings
        self.client = client

    def _repo(self, slug: str) -> Path:
        return self.settings.bundles_dir / slug

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

    @activity.defn
    def generate_changes(self, task: AgentTask) -> list[ArticleChange]:
        """Run the agent in a scratch worktree and return its edits as Article changes."""
        repo = self._repo(task.bundle)
        attempt = activity.info().attempt
        workspace = self.settings.scratch_dir / f"{task.proposal_id}-{attempt}"
        if workspace.exists():
            git.worktree_remove(repo, workspace)
            shutil.rmtree(workspace, ignore_errors=True)
        git.worktree_add(repo, workspace)
        try:
            fake.run(workspace, task)
            generated = {"by": "fake-agent", "at": datetime.now(UTC).isoformat(timespec="seconds")}
            changes = []
            for path in git.changed_paths(workspace):
                if not _is_article(path):
                    continue
                base_blob = git.blob(workspace, path)
                content = frontmatter.update((workspace / path).read_text(), generated=generated)
                meta, _ = frontmatter.split(content)
                changes.append(
                    ArticleChange(
                        id=_change_id(path),
                        path=path,
                        kind="update" if base_blob else "create",
                        base_blob=base_blob,
                        base_content=git.show(workspace, path) if base_blob else None,
                        content=content,
                        title=str(meta.get("title", path)),
                    )
                )
            return changes
        finally:
            git.worktree_remove(repo, workspace)
            shutil.rmtree(workspace, ignore_errors=True)

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
        now = datetime.now(UTC).isoformat(timespec="seconds")
        for change in req.changes:
            target = repo / change.path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = frontmatter.update(
                change.content,
                status="retired" if change.kind == "retire" else "accepted",
                review={"state": "accepted", "reviewer": req.reviewer, "reviewed_at": now},
            )
            target.write_text(content)
        message = (
            f"{req.title}\n\n"
            f"Proposal: {req.proposal_id}\n"
            f"Reviewed-by: {req.reviewer}\n"
        )
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
        return [self.init_bundle, self.generate_changes, self.commit_changes, self.commit_via_bundle]


def _email_local(name: str) -> str:
    local = "".join(ch if ch.isascii() and ch.isalnum() else "-" for ch in name.lower()).strip("-")
    return local or "reviewer"
