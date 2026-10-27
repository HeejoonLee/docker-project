import pytest
import shlex

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


def test_http_credentials_encoded_and_hidden():
    url = "https://gitlab.intra:8443/group/repo.git"
    authenticated = git.with_http_credentials(url, "user@example.com", "a@b:/?#%")
    assert git.http_credentials(authenticated) == ("user@example.com", "a@b:/?#%")
    assert git.public_url(authenticated) == url
    assert "a%40b" not in git.redact(authenticated)
    assert git.with_http_credentials(authenticated, None, "") == authenticated
    assert git.with_http_credentials(authenticated, None, remove=True) == url
    assert git.http_credentials(git.with_http_credentials(url, None, "token")) == ("oauth2", "token")


def test_ssh_url_uses_explicit_gerrit_port(tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    git.git(remote, "init", "-q", "--bare", "-b", "main")
    arguments = tmp_path / "ssh-args"
    transport = tmp_path / "ssh-transport"
    transport.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" > {shlex.quote(str(arguments))}\n"
        f"exec git-upload-pack {shlex.quote(str(remote))}\n"
    )
    transport.chmod(0o755)
    monkeypatch.setitem(git._ENV, "GIT_SSH_COMMAND", str(transport))
    monkeypatch.setitem(git._ENV, "GIT_SSH_VARIANT", "ssh")
    git.clone("ssh://user@gerrit.intra:29418/project.git", tmp_path / "clone")
    assert "-p\n29418\n" in arguments.read_text()


@pytest.mark.parametrize("url", ["", "/tmp/remote.git", "git@gitlab.intra:repo.git", "https:///repo.git"])
def test_tokens_require_http(url):
    with pytest.raises(ValueError, match="HTTP"):
        git.with_http_credentials(url, None, "secret")
    assert git.with_http_credentials(url, None) == url
