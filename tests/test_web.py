import asyncio
import json

import httpx
import pytest
import pytest_asyncio

from stonepedia.web import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def http(env, worker, settings):
    app.state.client = env.client
    app.state.settings = settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_propose_and_accept_over_http(http, uid):
    slug = f"w{uid}"
    r = await http.post("/api/bundles", json={"slug": slug, "name": "Web test"})
    assert r.status_code == 201
    # A Proposal can be created immediately after the Bundle.
    r = await http.post(
        "/api/proposals",
        data={"bundle": slug, "title": "부트 구성", "sources": _texts("Boot LU는 LU 1이다."), "submitted_by": "kim"},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    for _ in range(50):
        view = (await http.get(f"/api/proposals/{pid}")).json()
        if view["state"] == "awaiting_review":
            break
        await asyncio.sleep(0.1)
    [change] = view["changes"]
    assert change["path"] == f"notes/{pid}.md"  # non-ASCII title falls back to the Proposal id

    r = await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    assert r.status_code == 409 and "Decide on every change" in r.json()["detail"]

    await http.post(f"/api/proposals/{pid}/changes/{change['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    for _ in range(50):
        view = (await http.get(f"/api/proposals/{pid}")).json()
        if view["state"] == "done":
            break
        await asyncio.sleep(0.1)
    assert view["commit"]

    bundle = (await http.get(f"/api/bundles/{slug}")).json()
    assert [a["title"] for a in bundle["articles"]] == ["부트 구성"]
    article = (await http.get(f"/api/bundles/{slug}/articles/{change['path']}")).json()
    assert "Boot LU" in article["content"]
    assert (await http.get(f"/api/bundles/{slug}/articles/..%2F..%2Fetc%2Fpasswd.md")).status_code == 404


async def test_duplicate_and_invalid_bundles_rejected(http, uid):
    assert (await http.post("/api/bundles", json={"slug": f"d{uid}", "name": "x"})).status_code == 201
    assert (await http.post("/api/bundles", json={"slug": f"d{uid}", "name": "x"})).status_code == 409
    assert (await http.post("/api/bundles", json={"slug": "Bad Slug", "name": "x"})).status_code == 422


async def test_settings_roundtrip_and_validation(http):
    r = await http.get("/api/settings")
    assert r.status_code == 200 and "agent" not in r.json()["app"]  # the agent is not user-selectable
    bad = {"app": {"agent_timeout_minutes": 30}, "claude_settings": "{not json"}
    assert (await http.put("/api/settings", json=bad)).status_code == 422
    good = {"app": {"agent_timeout_minutes": 30}, "claude_settings": '{"model": "x"}'}
    assert (await http.put("/api/settings", json=good)).status_code == 200
    r = (await http.get("/api/settings")).json()
    assert r["app"]["agent_timeout_minutes"] == 30
    assert r["claude_settings"].strip() == '{"model": "x"}'


async def test_file_upload_commits_source_folder(http, settings, uid):
    from test_sources import make_docx

    slug = f"u{uid}"
    assert (await http.post("/api/bundles", json={"slug": slug, "name": "Upload test"})).status_code == 201
    doc = make_docx(settings.data_dir / "절차서.docx")
    r = await http.post(
        "/api/proposals",
        data={"bundle": slug, "sources": json.dumps([{"kind": "file"}]), "submitted_by": "kim"},
        files={"files": ("절차서.docx", doc.read_bytes())},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["title"] == "절차서.docx"
    view = await _wait(http, pid, "awaiting_review")
    [src] = view["sources"]
    assert src["id"] == f"{pid}-1" and src["media"] == "docx" and "부트 절차" in src["preview"]
    [change] = view["changes"]
    assert f"resource: ../sources/{pid}-1/original.docx" in change["content"]
    assert (await http.get(f"/api/proposals/{pid}/sources/{pid}-1/text.md")).status_code == 200
    assert (await http.get(f"/api/proposals/{pid}/sources/{pid}-1/..%2Fmeta.yaml")).status_code == 404
    assert (await http.get(f"/api/proposals/{pid}/sources/..%2F{pid}-1/text.md")).status_code == 404

    await http.post(f"/api/proposals/{pid}/changes/{change['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    await _wait(http, pid, "done")
    folder = settings.bundles_dir / slug / "sources" / f"{pid}-1"
    assert sorted(p.name for p in folder.iterdir()) == ["meta.yaml", "original.docx", "text.md"]


async def test_request_aimed_at_an_article(http, settings, uid):
    slug = f"q{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Request test"})
    r = await http.post("/api/proposals", data={"bundle": slug, "title": "Boot", "sources": _texts("Boot LU is 1.")})
    pid = r.json()["id"]
    [c] = (await _wait(http, pid, "awaiting_review"))["changes"]
    await http.post(f"/api/proposals/{pid}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    await _wait(http, pid, "done")

    r = await http.post(
        "/api/proposals",
        data={"bundle": slug, "request": "FFU 후 재부팅이 필요하다.", "targets": c["path"], "submitted_by": "park"},
    )
    assert r.json()["title"] == "FFU 후 재부팅이 필요하다."
    view = await _wait(http, r.json()["id"], "awaiting_review")
    [u] = view["changes"]
    assert u["kind"] == "update" and "Requested: FFU 후 재부팅이 필요하다." in u["content"]
    assert "author: human:park" in u["content"] and f"id: {pid}-1" in u["content"]  # both Sources cited
    assert view["targets"] == [c["path"]]


async def test_bad_submissions(http, settings, uid):
    slug = f"x{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "x"})
    def post(items, **kw):
        return http.post("/api/proposals", data={"bundle": slug, "sources": json.dumps(items)}, **kw)

    assert (await http.post("/api/proposals", data={"bundle": slug})).status_code == 422  # nothing given
    assert (await post([{"kind": "link", "url": "ftp://x"}])).status_code == 422
    assert (await post([{"kind": "file"}])).status_code == 422
    r = await post([{"kind": "text", "text": "a"}, {"kind": "file"}], files={"files": ("a.exe", b"MZ")})
    assert r.status_code == 422 and r.json()["detail"].startswith("Source 2: unsupported")
    r = await post([{"kind": "link", "url": "http://a/x"}, {"kind": "link", "url": "http://a/x"}])
    assert r.status_code == 422 and "already" in r.json()["detail"]
    assert (await post([{"kind": "text", "text": f"t{i}"} for i in range(21)])).status_code == 422
    assert not any((settings.uploads_dir).glob("*/2/a.exe"))


async def test_many_sources_and_a_request_in_one_proposal(http, settings, uid):
    from test_sources import make_docx

    slug = f"m{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Many"})
    doc = make_docx(settings.data_dir / f"spec{uid}.docx")
    items = [{"kind": "text", "text": "Boot LU is 1.", "title": "Meeting notes"}, {"kind": "file"},
             {"kind": "text", "text": "Reboot takes 40 s."}]
    r = await http.post("/api/proposals", data={
        "bundle": slug, "sources": json.dumps(items), "request": "Merge these into one boot guide.\nKeep it short.",
        "submitted_by": "kim",
    }, files={"files": ("spec.docx", doc.read_bytes())})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["title"] == "Merge these into one boot guide."
    view = await _wait(http, pid, "awaiting_review")
    assert [s["id"] for s in view["sources"]] == [f"{pid}-1", f"{pid}-2", f"{pid}-3"]
    assert [s["title"] for s in view["sources"]] == ["Meeting notes", "spec.docx", "Reboot takes 40 s."]
    assert view["request"]["id"] == f"{pid}-4" and view["request"]["kind"] == "request"
    [c] = view["changes"]
    assert "Boot LU is 1." in c["content"] and "Reboot takes 40 s." in c["content"] and "부트 절차" in c["content"]
    for n in range(1, 5):
        assert f"id: {pid}-{n}" in c["content"]

    await http.post(f"/api/proposals/{pid}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    await _wait(http, pid, "done")
    committed = sorted(p.name for p in (settings.bundles_dir / slug / "sources").iterdir())
    assert committed == [f"{pid}-{n}" for n in range(1, 5)]
    from stonepedia import git
    log = git.git(settings.bundles_dir / slug, "log", "-1", "--format=%B")
    assert f"Source: sources/{pid}-2/" in log
    assert "Request by kim:\n> Merge these into one boot guide.\n> Keep it short." in log


async def test_unreadable_source_fails_the_proposal_and_names_it(http, settings, uid):
    slug = f"f{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Fail"})
    items = [{"kind": "text", "text": "Boot LU is 1."}, {"kind": "file"}]
    r = await http.post("/api/proposals", data={"bundle": slug, "sources": json.dumps(items)},
                        files={"files": ("broken.pdf", b"not a pdf")})
    view = await _wait(http, r.json()["id"], "failed")
    assert "Source 2 (broken.pdf): Could not read the PDF" in view["error"]
    assert not list(settings.sources_dir.glob(f"{view['id']}-*"))


def _texts(*texts):
    return json.dumps([{"kind": "text", "text": t} for t in texts])


async def _wait(http, pid, state):
    for _ in range(100):
        view = (await http.get(f"/api/proposals/{pid}")).json()
        if view["state"] == state:
            return view
        await asyncio.sleep(0.1)
    raise AssertionError(f"{view['state']}: {view.get('error')}")


async def test_config_points_at_proxied_temporal_ui_and_health(http):
    r = (await http.get("/api/config")).json()
    assert r == {"temporal_ui_url": "/temporal", "namespace": "default"}
    assert (await http.get("/api/health")).json() == {"ok": True}
