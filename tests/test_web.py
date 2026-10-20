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
        json={"bundle": slug, "title": "부트 구성", "text": "Boot LU는 LU 1이다.", "submitted_by": "kim"},
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
    assert r["app"] == {"agent": "claude-cli", "agent_timeout_minutes": 30}
    assert r["claude_settings"].strip() == '{"model": "x"}'
