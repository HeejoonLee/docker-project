import pytest

from stonepedia import git


def test_sync_conflict_aborts_and_keeps_local_commit(tmp_path):
    remote = tmp_path / "r.git"
    remote.mkdir()
    git.git(remote, "init", "-q", "--bare", "-b", "main")
    a, b = tmp_path / "a", tmp_path / "b"
    git.init(a)
    (a / "f.md").write_text("one\n")
    git.commit_all(a, "init", ("A", "a@x"))
    git.set_remote(a, str(remote))
    git.push(a, "main")
    git.clone(str(remote), b)

    (b / "f.md").write_text("from b\n")
    git.commit_all(b, "b", ("B", "b@x"))
    git.push(b, "main")
    (a / "f.md").write_text("from a\n")
    local = git.commit_all(a, "a", ("A", "a@x"))

    with pytest.raises(git.GitError, match="conflict"):
        git.sync(a, "main")
    assert git.head(a) == local and git.is_clean(a)


def test_redact():
    assert git.redact("http://bot:tok@h/x.git") == "http://bot:***@h/x.git"
    assert git.redact("http://h/x.git") == "http://h/x.git"
