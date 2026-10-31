import asyncio
import json
import http.server as httpserver
import threading

import httpx
import pytest
import pytest_asyncio
import yaml

from stonepedia import bundle, maintenance
from stonepedia.web import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def http(env, worker, settings):
    app.state.client = env.client
    app.state.settings = settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


async def test_integrity_findings(tmp_path):
    repo = tmp_path
    root = repo / "kb"
    bundle.save_settings(root, bundle.BundleSettings(name="x", id_prefix="K-"))
    bundle.save_template(root, bundle.load_template(root))
    write(root / "a.md", "---\ntype: Guidance\ntitle: A\ndescription: d\nid: K-01\nsources:\n- id: s1\n  resource: sources/s1/text.md\n---\n\n"
          "See [B](b.md), [gone](missing.md), [spec](../docs/spec.md#x), [web](https://x.y) and [top](#a).\n")
    write(root / "b.md", "---\ntype: Recipe\ntitle: B\nid: K-01\nsources:\n- id: s2\n  resource: sources/s2/nope.md\n---\n\nbody\n")
    write(root / "c.md", "no frontmatter\n")
    write(root / "old.md", "---\ntype: Guidance\nstatus: retired\n---\n\n[dead](dead.md)\n")
    write(repo / "docs/spec.md", "spec")
    write(root / "sources/s1/text.md", "t")
    write(root / "sources/s2/text.md", "t")
    write(root / "sources/s3/text.md", "t")

    found = {(f.kind, f.path, f.message) for f in maintenance.check(root, repo)}
    kinds = sorted(k for k, _, _ in found)
    assert kinds == ["broken_link", "duplicate_id", "missing_field", "missing_source", "no_frontmatter",
                     "uncited_source", "unknown_type"]
    assert ("broken_link", "a.md", "Link target not found: missing.md") in found
    assert ("missing_field", "b.md", "Required field 'description' is missing.") in found
    assert ("uncited_source", "sources/s3", "No Article cites this Source.") in found


async def _report(http, slug, check):
    r = await http.post(f"/api/maintenance/{slug}/run/{check}", json={"requested_by": "kim"})
    assert r.status_code == 200, r.text
    wid, rid = r.json()["workflow_id"], r.json()["run_id"]
    for _ in range(150):
        report = (await http.get(f"/api/maintenance/reports/{wid}/{rid}")).json()
        if report:
            return report
        await asyncio.sleep(0.1)
    raise AssertionError("no report")


async def _wait(http, pid, states=("awaiting_review",)):
    for _ in range(150):
        v = (await http.get(f"/api/proposals/{pid}")).json()
        if v["state"] in states:
            return v
        await asyncio.sleep(0.1)
    raise AssertionError(v["state"])


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    page = root / "spec.html"
    page.write_text("<html><title>Spec</title><body><p>" + "Boot LU is 1. " * 30 + "</p></body></html>")
    handler = lambda *a, **kw: httpserver.SimpleHTTPRequestHandler(*a, directory=str(root), **kw)  # noqa: E731
    server = httpserver.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", page
    server.shutdown()


async def test_link_refresh_opens_one_proposal_per_change(http, settings, site, uid):
    url, page = site
    slug = f"m{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Links"})
    r = await http.post("/api/proposals", data={"bundle": slug, "sources": json.dumps([{"kind": "link", "url": f"{url}/spec.html"}])})
    view = await _wait(http, r.json()["id"])
    assert view["title"] == "Spec"  # untitled link takes the page title
    for c in view["changes"]:
        await http.post(f"/api/proposals/{view['id']}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{view['id']}/submit", json={"reviewer": "lee"})
    await _wait(http, view["id"], ("done",))

    unchanged = await _report(http, slug, "links")
    assert unchanged["proposals"] == [] and unchanged["summary"] == "0 changed, 0 unreachable"

    page.write_text("<html><title>Spec</title><body><p>" + "Boot LU is 2 now. " * 30 + "</p></body></html>")
    changed = await _report(http, slug, "links")
    [pid] = changed["proposals"]
    refresh = await _wait(http, pid)
    assert refresh["origin"] == "maintenance" and refresh["title"] == "Updated: Spec"
    assert view["id"] in refresh["note"] and refresh["submitted_by"] == "Stonepedia maintenance"

    again = await _report(http, slug, "links")
    assert again["proposals"] == []  # the same change is not proposed twice

    overview = (await http.get(f"/api/maintenance/{slug}")).json()
    assert [r["check"] for r in overview["reports"]] == ["links"] * 3
    assert all(r["requested_by"] == "kim" and r["status"] == "completed" for r in overview["reports"])


async def test_integrity_run_and_schedules(http, uid):
    slug = f"i{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Integrity"})
    report = await _report(http, slug, "integrity")
    assert report["summary"] == "No problems found"

    r = await http.put(f"/api/maintenance/{slug}/schedules/integrity", json={"cadence": "weekly", "time": "04:30", "weekday": 1})
    assert r.status_code == 200, r.text
    assert r.json()["cadence"] == "weekly" and r.json()["time"] == "04:30" and r.json()["weekday"] == 1
    assert r.json()["next_run"]
    r = await http.put(f"/api/maintenance/{slug}/schedules/integrity", json={"cadence": "daily", "time": "02:00"})
    assert r.json()["cadence"] == "daily" and r.json()["time"] == "02:00"
    overview = (await http.get(f"/api/maintenance/{slug}")).json()
    assert overview["schedules"]["integrity"]["cadence"] == "daily"
    assert overview["schedules"]["links"]["cadence"] == "off"
    await http.put(f"/api/maintenance/{slug}/schedules/integrity", json={"cadence": "off"})
    assert (await http.get(f"/api/maintenance/{slug}")).json()["schedules"]["integrity"]["cadence"] == "off"
    bad = await http.put(f"/api/maintenance/{slug}/schedules/integrity", json={"cadence": "daily", "time": "25:00"})
    assert bad.status_code == 422


async def test_audit_proposal_does_not_cite_itself(http, settings, uid):
    slug = f"a{uid}"
    await http.post("/api/bundles", json={"slug": slug, "name": "Audit"})
    r = await http.post(f"/api/bundles/{slug}/audit", json={"requested_by": "kim", "focus": "FFU docs"})
    assert r.status_code == 201 and r.json()["title"] == "AI audit: FFU docs"
    view = await _wait(http, r.json()["id"])
    assert view["request"]["kind"] == "audit" and view["sources"] == []
    [c] = view["changes"]
    assert "sources:" not in c["content"]
    await http.post(f"/api/proposals/{view['id']}/changes/{c['id']}/decision", json={"decision": "accepted"})
    await http.post(f"/api/proposals/{view['id']}/submit", json={"reviewer": "lee"})
    await _wait(http, view["id"], ("done",))
    assert not (settings.bundles_dir / slug / "sources").exists()
    meta = yaml.safe_load((settings.sources_dir / view["request"]["id"] / "meta.yaml").read_text())
    assert meta["kind"] == "audit"
