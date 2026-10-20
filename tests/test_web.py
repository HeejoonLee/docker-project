import asyncio

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
        data={"bundle": slug, "kind": "text", "title": "부트 구성", "text": "Boot LU는 LU 1이다.", "submitted_by": "kim"},
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
    assert r.status_code == 200 and r.json()["app"]["agent"] == "fake"
    bad = {"app": {"agent": "claude-cli", "agent_timeout_minutes": 30}, "claude_settings": "{not json"}
    assert (await http.put("/api/settings", json=bad)).status_code == 422
    good = {"app": {"agent": "claude-cli", "agent_timeout_minutes": 30}, "claude_settings": '{"model": "x"}'}
    assert (await http.put("/api/settings", json=good)).status_code == 200
    r = (await http.get("/api/settings")).json()
    assert r["app"]["agent"] == "claude-cli" and r["app"]["agent_timeout_minutes"] == 30
    assert r["claude_settings"].strip() == '{"model": "x"}'


async def test_file_upload_commits_source_folder(http, settings, uid):
    from test_sources import make_docx

    slug = f"u{uid}"
    assert (await http.post("/api/bundles", json={"slug": slug, "name": "Upload test"})).status_code == 201
    doc = make_docx(settings.data_dir / "절차서.docx")
    r = await http.post(
        "/api/proposals",
        data={"bundle": slug, "kind": "file", "submitted_by": "kim"},
        files={"file": ("절차서.docx", doc.read_bytes())},
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["title"] == "절차서.docx"
    view = await _wait(http, pid, "awaiting_review")
    assert view["source"]["media"] == "docx" and "부트 절차" in view["source"]["preview"]
    [change] = view["changes"]
    assert f"resource: ../sources/{pid}/original.docx" in change["content"]
    assert (await http.get(f"/api/proposals/{pid}/source/text.md")).status_code == 200
    assert (await http.get(f"/api/proposals/{pid}/source/..%2Fmeta.yaml")).status_code == 404

    await http.post(f"/api/proposals/{pid}/changes/{change['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    await _wait(http, pid, "done")
    folder = settings.bundles_dir / slug / "sources" / pid
    assert sorted(p.name for p in folder.iterdir()) == ["meta.yaml", "original.docx", "text.md"]


async def test_request_aimed_at_an_article(http, settings, uid):
    slug = f"q{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Request test"})
    r = await http.post("/api/proposals", data={"bundle": slug, "kind": "text", "title": "Boot", "text": "Boot LU is 1."})
    pid = r.json()["id"]
    [c] = (await _wait(http, pid, "awaiting_review"))["changes"]
    await http.post(f"/api/proposals/{pid}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})
    await _wait(http, pid, "done")

    r = await http.post(
        "/api/proposals",
        data={"bundle": slug, "kind": "request", "text": "FFU 후 재부팅이 필요하다.", "targets": c["path"], "submitted_by": "park"},
    )
    assert r.json()["title"] == "FFU 후 재부팅이 필요하다."
    view = await _wait(http, r.json()["id"], "awaiting_review")
    [u] = view["changes"]
    assert u["kind"] == "update" and "Requested: FFU 후 재부팅이 필요하다." in u["content"]
    assert "author: human:park" in u["content"] and "id: " + pid in u["content"]  # both Sources cited
    assert view["targets"] == [c["path"]]


async def test_bad_submissions(http, uid):
    slug = f"x{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "x"})
    assert (await http.post("/api/proposals", data={"bundle": slug, "kind": "link", "url": "ftp://x"})).status_code == 422
    assert (await http.post("/api/proposals", data={"bundle": slug, "kind": "file"})).status_code == 422
    r = await http.post("/api/proposals", data={"bundle": slug, "kind": "file"}, files={"file": ("a.exe", b"MZ")})
    assert r.status_code == 422 and "Unsupported" in r.json()["detail"]


async def _wait(http, pid, state):
    for _ in range(100):
        view = (await http.get(f"/api/proposals/{pid}")).json()
        if view["state"] == state:
            return view
        await asyncio.sleep(0.1)
    raise AssertionError(f"{view['state']}: {view.get('error')}")
