"""Thin wrapper over the git CLI for Bundle repositories."""

import os
import subprocess
from pathlib import Path

SYSTEM_AUTHOR = ("Stonepedia", "stonepedia@stonepedia.local")


# Ignore host/user git config so behaviour is the same in dev and in the container.
_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_COUNT": "1",
    "GIT_CONFIG_KEY_0": "safe.directory",
    "GIT_CONFIG_VALUE_0": "*",
    "GIT_TERMINAL_PROMPT": "0",
}


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=_ENV,
    )
    if check and proc.returncode != 0:
        raise GitError(redact(f"git {' '.join(args)} failed: {proc.stderr.strip()}"))
    return proc.stdout


def init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def blob(repo: Path, path: str, rev: str = "HEAD") -> str | None:
    """Blob id of `path` at `rev`, or None if it does not exist there."""
    out = git(repo, "rev-parse", "-q", "--verify", f"{rev}:{path}", check=False).strip()
    return out or None


def show(repo: Path, path: str, rev: str = "HEAD") -> str | None:
    if blob(repo, path, rev) is None:
        return None
    return git(repo, "show", f"{rev}:{path}")


def is_clean(repo: Path) -> bool:
    return git(repo, "status", "--porcelain").strip() == ""


def changed_paths(repo: Path) -> list[str]:
    """Paths added or modified in the working tree (untracked files included)."""
    out = git(repo, "status", "--porcelain", "-uall", "-z")
    paths = []
    for entry in out.split("\0"):
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        if "D" not in status:
            paths.append(path)
    return sorted(paths)


def worktree_add(repo: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-q", "--detach", str(dest), "HEAD")


def worktree_remove(repo: Path, dest: Path) -> None:
    git(repo, "worktree", "remove", "--force", str(dest), check=False)
    git(repo, "worktree", "prune", check=False)


def commit_all(repo: Path, message: str, author: tuple[str, str]) -> str:
    name, email = author
    git(repo, "add", "-A")
    git(
        repo,
        "-c", f"user.name={name}",
        "-c", f"user.email={email}",
        "commit", "-q", "-m", message,
    )
    return head(repo)


def deleted_paths(repo: Path) -> list[str]:
    """Tracked paths deleted in the working tree."""
    out = git(repo, "status", "--porcelain", "-z")
    return sorted(e[3:] for e in out.split("\0") if e and "D" in e[:2])


def clone(url: str, dest: Path, branch: str = "") -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "-q"]
    if branch:
        args += ["-b", branch]
    git(dest.parent, *args, url, str(dest))


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()


def set_remote(repo: Path, url: str) -> None:
    if git(repo, "remote", check=False).split().count("origin"):
        if url:
            git(repo, "remote", "set-url", "origin", url)
        else:
            git(repo, "remote", "remove", "origin")
    elif url:
        git(repo, "remote", "add", "origin", url)


def sync(repo: Path, branch: str) -> None:
    """Fetch origin and rebase local commits on top of it.

    Raises GitError (after aborting the rebase, so nothing is lost) when they conflict.
    """
    git(repo, "fetch", "-q", "origin")
    if blob_ref(repo, f"origin/{branch}") is None:
        return  # first push will create the remote branch
    try:
        git(repo, "-c", "user.name=Stonepedia", "-c", "user.email=stonepedia@stonepedia.local",
            "rebase", "-q", f"origin/{branch}")
    except GitError:
        if _rebasing(repo):
            git(repo, "rebase", "--abort", check=False)
        raise GitError(
            f"Local commits conflict with changes on origin/{branch}. They stay here unpushed; "
            "resolve the conflict with a git client."
        ) from None


def _rebasing(repo: Path) -> bool:
    gitdir = Path(git(repo, "rev-parse", "--absolute-git-dir").strip())
    return (gitdir / "rebase-merge").exists() or (gitdir / "rebase-apply").exists()


def blob_ref(repo: Path, ref: str) -> str | None:
    out = git(repo, "rev-parse", "-q", "--verify", ref, check=False).strip()
    return out or None


def push(repo: Path, branch: str) -> None:
    git(repo, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")


def ahead_count(repo: Path, branch: str) -> int:
    """Local commits not on origin/<branch> (all commits if the remote branch is unknown)."""
    if blob_ref(repo, f"origin/{branch}") is None:
        return int(git(repo, "rev-list", "--count", "HEAD").strip())
    return int(git(repo, "rev-list", "--count", f"origin/{branch}..HEAD").strip())


def redact(url: str) -> str:
    """Hide a password/token embedded in a remote URL."""
    import re

    return re.sub(r"(://[^/@:]+):[^/@]+@", r"\1:***@", url)
