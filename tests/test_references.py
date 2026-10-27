import asyncio
import hashlib

import httpx
import pytest
import pytest_asyncio

from stonepedia import frontmatter, references
from stonepedia.models import BundleSpec
from stonepedia.web import app

@pytest_asyncio.fixture(loop_scope="session")
async def http(env, worker, settings):
    app.state.client = env.client
    app.state.settings = settings
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def ready(http, proposal_id, state="awaiting_review"):
    for _ in range(100):
        result = await http.get(f"/api/proposals/{proposal_id}")
        assert result.status_code == 200, result.text
        view = result.json()
        if view["state"] == state:
            return view
        await asyncio.sleep(0.1)
    raise AssertionError(f"Proposal stayed {view['state']}: {view['error']}")


def test_citations_allow_plain_directory_and_detect_file_changes(tmp_path):
    root = tmp_path / "references"
    project = root / "project"
    project.mkdir(parents=True)
    file = project / "app.py"
    file.write_text("print('one')\n")
    spec = BundleSpec(slug="demo", name="Demo", reference_dir="project")
    directory = references.resolve(root, spec.reference_dir)
    assert directory == project
    item = references.citation(directory, spec, "app.py")
    assert item["sha256"] == hashlib.sha256(file.read_bytes()).hexdigest()
    assert references.changed(root, spec, [item]) == []
    file.write_text("print('two')\n")
    assert references.changed(root, spec, [item]) == ["app.py"]
    with pytest.raises(ValueError):
        references.resolve(root, "../outside")
    with pytest.raises(ValueError):
        references.citation(directory, spec, "../other.py")


@pytest.mark.asyncio(loop_scope="session")
async def test_code_proposal_refreshes_stale_citation(http, settings, uid):
    directory = settings.reference_root / f"code-{uid}"
    directory.mkdir(parents=True)
    code = directory / "boot.py"
    code.write_text("BOOT_LU = 1\n")
    slug = f"code{uid}"
    created = await http.post("/api/bundles", json={"slug": slug, "name": "Code"})
    assert created.status_code == 201, created.text
    unavailable = await http.post("/api/proposals", data={
        "bundle": slug, "kind": "code", "text": "Document the boot flow",
    })
    assert unavailable.status_code == 422
    detail = (await http.get(f"/api/bundles/{slug}")).json()
    updated = await http.put(f"/api/bundles/{slug}/settings", json={
        "editor": "kim", "settings": detail["settings"], "remote_url": detail["remote_url"],
        "branch": detail["branch"], "reference_dir": directory.name,
        "reference_excludes": [".env*", "dist"],
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["reference_dir"] == directory.name
    assert updated.json()["reference_excludes"] == [".env*", "dist"]

    proposal = await http.post("/api/proposals", data={
        "bundle": slug, "kind": "code", "text": "Document the boot flow", "title": "Boot flow", "submitted_by": "kim",
    })
    assert proposal.status_code == 201, proposal.text
    pid = proposal.json()["id"]
    view = await ready(http, pid)
    [change] = view["changes"]
    meta, _ = frontmatter.split(change["content"])
    [citation] = [s for s in meta["sources"] if s.get("kind") == "code"]
    assert citation["path"] == "boot.py"
    assert citation["sha256"] == hashlib.sha256(code.read_bytes()).hexdigest()
    assert "code_refs" not in meta

    code.write_text("BOOT_LU = 2\n")
    stale = (await http.get(f"/api/proposals/{pid}")).json()
    assert stale["code_stale_paths"] == ["boot.py"]
    blocked = await http.post(f"/api/proposals/{pid}/changes/{change['id']}/decision", json={"decision": "accepted"})
    assert blocked.status_code == 409

    refreshed = await http.post(f"/api/proposals/{pid}/refresh-code", json={"reviewer": "lee"})
    assert refreshed.status_code == 200, refreshed.text
    view = await ready(http, pid)
    [change] = view["changes"]
    assert view["code_stale_paths"] == []
    meta, _ = frontmatter.split(change["content"])
    [citation] = [s for s in meta["sources"] if s.get("kind") == "code"]
    assert citation["sha256"] == hashlib.sha256(code.read_bytes()).hexdigest()
    assert (await http.post(f"/api/proposals/{pid}/changes/{change['id']}/decision", json={"decision": "accepted"})).status_code == 200
    assert (await http.post(f"/api/proposals/{pid}/submit", json={"reviewer": "lee"})).status_code == 200
    await ready(http, pid, "done")
