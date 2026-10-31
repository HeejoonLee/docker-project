"""Bundles as git repos: import, remotes, ids, index, retire, Template and settings."""

import asyncio
import json
import shutil
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import yaml

from stonepedia import frontmatter, git
from stonepedia.web import app
from git_http import authenticated_remote

pytestmark = pytest.mark.asyncio(loop_scope="session")

KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge"


@pytest_asyncio.fixture(loop_scope="session")
async def http(env, worker, settings):
    app.state.client = env.client
    app.state.settings = settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def bare_repo(tmp_path: Path, name: str, source: Path | None = None) -> Path:
    remote = tmp_path / f"{name}.git"
    if source:
        git.git(tmp_path, "clone", "-q", "--bare", str(source), str(remote))
    else:
        remote.mkdir()
        git.git(remote, "init", "-q", "--bare", "-b", "main")
    return remote


async def until(check, tries=150):
    for _ in range(tries):
        result = await check()
        if result:
            return result
        await asyncio.sleep(0.1)
    raise AssertionError("condition not reached")


async def propose(http, slug, kind, text, **data):
    if kind == "request":
        data["request"] = text
    else:
        data["sources"] = json.dumps([{"kind": kind, "text": text}])
    r = await http.post("/api/proposals", data={"bundle": slug, "submitted_by": "kim", **data})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    async def ready():
        v = (await http.get(f"/api/proposals/{pid}")).json()
        return v if v["state"] not in ("generating", "committing") else None

    return await until(ready)


async def accept_all(http, view, reviewer="lee"):
    for c in view["changes"]:
        await http.post(f"/api/proposals/{view['id']}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{view['id']}/submit", json={"reviewer": reviewer})

    async def done():
        v = (await http.get(f"/api/proposals/{view['id']}")).json()
        finished = v["state"] == "done" or (v["state"] == "awaiting_review" and any(c["stale"] for c in v["changes"]))
        return v if finished else None

    return await until(done)


async def pushed(http, slug):
    async def ok():
        b = (await http.get(f"/api/bundles/{slug}")).json()
        return b if b["push"]["state"] in ("ok", "failed") else None

    return await until(ok)


async def test_new_bundle_pushes_and_indexes(http, settings, tmp_path, uid):
    remote = bare_repo(tmp_path, "fresh")
    slug = f"n{uid}"
    r = await http.post("/api/bundles", json={"slug": slug, "name": "Fresh", "id_prefix": "KB-", "remote_url": str(remote)})
    assert r.status_code == 201, r.text
    assert (await pushed(http, slug))["push"]["state"] == "ok"

    view = await propose(http, slug, kind="text", title="Boot", text="Boot from LU 1.")
    await accept_all(http, view)
    detail = await pushed(http, slug)
    assert detail["push"]["state"] == "ok"
    [article] = detail["articles"]
    assert article["id"] == "KB-01" and article["path"] == "notes/boot.md"

    repo = settings.bundles_dir / slug
    index = (repo / "index.md").read_text()
    assert "| KB-01 | [Boot](notes/boot.md) | Guidance | accepted |" in index
    manifest = json.loads((repo / "manifest.json").read_text())
    assert manifest["document_count"] == 1 and manifest["documents"][0]["id"] == "KB-01"
    assert git.git(remote, "log", "-1", "--format=%an %s", "main").strip() == "lee Boot"
    assert "[KB-01]" in git.git(remote, "log", "-1", "--format=%B", "main")


@pytest.mark.skipif(not (KNOWLEDGE / ".git").exists(), reason="../knowledge reference repo not present")
async def test_import_knowledge_subfolder(http, settings, tmp_path, uid):
    remote = bare_repo(tmp_path, "knowledge", KNOWLEDGE)
    slug = f"k{uid}"
    r = await http.post("/api/bundles", json={
        "slug": slug, "name": "BL·KD", "clone_url": str(remote), "branch": "", "root": "knowledge/bl-kd",
    })
    assert r.status_code == 201, r.text
    detail = (await http.get(f"/api/bundles/{slug}")).json()
    assert detail["root"] == "knowledge/bl-kd" and len(detail["articles"]) == 18
    assert detail["settings"]["id_field"] == "cornerstone.knowledge_id"
    assert detail["settings"]["id_prefix"] == "BK-"
    # existing hand-written index and manifest are left alone
    assert detail["settings"]["generate_index"] is False and detail["settings"]["generate_manifest"] is False

    template = (await http.get(f"/api/bundles/{slug}/template")).json()
    assert {t["name"] for t in template["types"]} == {"Specification", "Guidance", "Decision"}
    assert "cornerstone" in [f["name"] for f in template["fields"] if f["written_by"] == "ai"]

    assert any(a["id"] == "BK-04" for a in detail["articles"])

    # A Request aimed at an existing Article keeps its cornerstone profile block.
    target = "bootloader/factory-dm-ffu.md"
    view = await propose(http, slug, kind="request", text="FFU 후 재부팅이 필요하다.", targets=target)
    [change] = view["changes"]
    assert change["path"] == target and change["kind"] == "update"
    meta, _ = frontmatter.split(change["content"])
    assert meta["cornerstone"]["knowledge_id"] == "BK-04" and meta["cornerstone"]["wbs_steps"]
    ids = [s.get("id") for s in meta["sources"]]
    assert "wbs" in ids and f"{view['id']}-1" in ids  # original sources kept, the Request added

    new = await propose(http, slug, kind="text", title="Reboot timing", text="Reboot takes 40 s.")
    await accept_all(http, view)
    await accept_all(http, new)
    detail = await pushed(http, slug)
    assert detail["push"]["state"] == "ok", detail["push"]
    created = next(a for a in detail["articles"] if a["path"] == "notes/reboot-timing.md")
    assert created["id"] == "BK-19"

    repo = settings.bundles_dir / slug
    assert (repo / "knowledge/bl-kd/notes/reboot-timing.md").exists()
    assert (repo / "knowledge/bl-kd/sources" / f"{new['id']}-1" / "text.md").exists()
    assert not (repo / "notes").exists()
    log = git.git(remote, "log", "--format=%an|%s", "-4", "HEAD")
    assert "lee|Reboot timing" in log and "Stonepedia|Set up Stonepedia" in log


async def test_retire_marks_article(http, settings, uid):
    slug = f"r{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Retire"})
    view = await propose(http, slug, kind="text", title="Old fact", text="Obsolete.")
    await accept_all(http, view)
    path = view["changes"][0]["path"]

    view = await propose(http, slug, kind="request", text="RETIRE: merged elsewhere", targets=path)
    [change] = view["changes"]
    assert change["kind"] == "retire"
    await accept_all(http, view)
    meta, _ = frontmatter.split((settings.bundles_dir / slug / path).read_text())
    assert meta["status"] == "retired" and meta["review"]["reviewer"] == "lee"


async def test_template_edit_is_committed(http, settings, uid):
    slug = f"t{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Tmpl"})
    template = (await http.get(f"/api/bundles/{slug}/template")).json()
    template["types"].append({"name": "Procedure", "rule": "Step-by-step work instructions.", "sections": ["Steps"]})
    template["guidance"] = "Write short sentences."
    r = await http.put(f"/api/bundles/{slug}/template", json={"editor": "choi", "template": template})
    assert r.status_code == 200
    stored = yaml.safe_load((settings.bundles_dir / slug / ".stonepedia/template.yaml").read_text())
    assert stored["types"][-1]["name"] == "Procedure" and stored["guidance"] == "Write short sentences."
    assert git.git(settings.bundles_dir / slug, "log", "-1", "--format=%an|%s").strip() == "choi|Update Bundle template"
    bad = {"editor": "choi", "template": {"types": [], "fields": [], "guidance": ""}}
    assert (await http.put(f"/api/bundles/{slug}/template", json=bad)).status_code == 422


async def test_remote_edits_make_changes_stale(http, settings, tmp_path, uid):
    remote = bare_repo(tmp_path, "shared")
    slug = f"s{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Shared", "remote_url": str(remote)})
    first = await propose(http, slug, kind="text", title="Boot", text="Boot from LU 1.")
    await accept_all(http, first)
    await pushed(http, slug)

    second = await propose(http, slug, kind="request", text="Mention LU 2.", targets="notes/boot.md")

    # Someone edits the same Article directly in the remote.
    other = tmp_path / "other"
    git.clone(str(remote), other)
    article = other / "notes/boot.md"
    article.write_text(article.read_text() + "\nEdited on GitLab.\n")
    git.commit_all(other, "Direct edit", ("Kang", "kang@x"))
    git.push(other, "main")

    result = await accept_all(http, second)
    assert result["state"] == "awaiting_review" and result["changes"][0]["stale"]
    assert "Edited on GitLab." in (settings.bundles_dir / slug / "notes/boot.md").read_text()  # pulled in


async def test_bad_clone_reports_error_and_slug_can_be_reused(http, tmp_path, uid):
    slug = f"b{uid}"
    r = await http.post("/api/bundles", json={"slug": slug, "name": "x", "clone_url": str(tmp_path / "nope.git")})
    assert r.status_code == 422 and "Could not create the Bundle" in r.json()["detail"]
    r = await http.post("/api/bundles", json={"slug": slug, "name": "x"})
    assert r.status_code == 201, r.text


async def test_http_token_clone_push_rotate_preserve_and_remove(http, settings, tmp_path, uid):
    seed = tmp_path / "seed"
    git.init(seed)
    (seed / "README.md").write_text("Private knowledge\n")
    git.commit_all(seed, "Initial knowledge", git.SYSTEM_AUTHOR)
    remote = bare_repo(tmp_path, "remote", seed)
    with authenticated_remote(tmp_path, token="first@token:/?#%") as server:
        slug = f"auth{uid}"
        r = await http.post("/api/bundles", json={
            "slug": slug, "name": "Private", "clone_url": server.url, "git_token": server.token,
        })
        assert r.status_code == 201, r.text
        detail = await pushed(http, slug)
        assert detail["push"]["state"] == "ok", detail["push"]
        assert detail["remote_url"] == detail["clone_url"] == server.url
        assert detail["git_token_configured"] and detail["git_username"] == "oauth2"
        assert server.token not in json.dumps(detail)
        assert git.git(remote, "log", "-1", "--format=%s").strip() == "Set up Stonepedia"

        repo = settings.bundles_dir / slug
        async def save(**credentials):
            r = await http.put(f"/api/bundles/{slug}/settings", json={
                "editor": "kim", "settings": detail["settings"],
                "remote_url": detail["remote_url"], "branch": detail["branch"], **credentials,
            })
            assert r.status_code == 200, r.text
            assert server.token not in r.text
            return r.json()

        # Blank and omitted tokens preserve authentication across ordinary saves.
        await save(git_token="")
        await save()
        assert git.http_credentials(git.git(repo, "remote", "get-url", "origin").strip()) == ("oauth2", server.token)

        # Rotated credentials must actually authenticate subsequent fetches and pushes.
        server.username, server.token = "git-bot", "replacement@token:/?#%"
        detail["settings"]["name"] = "Rotated"
        detail = await save(git_username=server.username, git_token=server.token)
        assert (await pushed(http, slug))["push"]["state"] == "ok"
        assert git.git(remote, "log", "-1", "--format=%s").strip() == "Update Bundle settings"
        assert git.http_credentials(git.git(repo, "remote", "get-url", "origin").strip()) == (server.username, server.token)

        detail = await save(remove_git_token=True)
        assert not detail["git_token_configured"]
        assert git.git(repo, "remote", "get-url", "origin").strip() == server.url


async def test_http_token_for_new_bundle_and_failed_clone_is_hidden(http, tmp_path, uid):
    bare_repo(tmp_path, "remote")
    with authenticated_remote(tmp_path) as server:
        slug = f"newauth{uid}"
        r = await http.post("/api/bundles", json={
            "slug": slug, "name": "Private", "remote_url": server.url, "git_token": server.token,
        })
        assert r.status_code == 201, r.text
        assert (await pushed(http, slug))["push"]["state"] == "ok"

        r = await http.post("/api/bundles", json={
            "slug": f"badauth{uid}", "name": "Private", "clone_url": server.url, "git_token": "wrong-token",
        })
        assert r.status_code == 422 and "wrong-token" not in r.text


async def test_token_requires_http_remote(http, uid):
    r = await http.post("/api/bundles", json={"slug": f"token{uid}", "name": "x", "git_token": "secret"})
    assert r.status_code == 422 and "HTTP(S)" in r.text and "secret" not in r.text
