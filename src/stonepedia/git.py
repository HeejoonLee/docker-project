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
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
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
