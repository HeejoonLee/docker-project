import json

import httpx
import pytest

from stonepedia.web import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_proxies_temporal_ui_under_prefix():
    seen = []

    def upstream(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/temporal/old":
            return httpx.Response(302, headers={"location": "http://ui.internal:8080/temporal/new"}, stream=httpx.ByteStream(b""))
        body = json.dumps({"path": req.url.path, "q": req.url.query.decode()}).encode()
        return httpx.Response(200, stream=httpx.ByteStream(body))  # streamed, like a real upstream

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream), base_url="http://ui.internal:8080") as ui:
        app.state.temporal_ui = ui
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://kb.intra") as http:
            r = await http.get("/temporal/api/v1/namespaces?x=1")
            assert r.json() == {"path": "/temporal/api/v1/namespaces", "q": "x=1"}
            assert seen[-1].headers["host"] == "ui.internal:8080"

            r = await http.post("/temporal/api/v1/x", content=b"body")
            assert seen[-1].method == "POST" and seen[-1].content == b"body"

            r = await http.get("/temporal/old")  # upstream redirects stay on our host
            assert r.status_code == 302 and r.headers["location"] == "/temporal/new"

            r = await http.get("/temporal")
            assert r.status_code == 307 and r.headers["location"] == "/temporal/"


async def test_temporal_ui_down_is_a_502():
    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://ui.internal:8080") as ui:
        app.state.temporal_ui = ui
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://kb.intra") as http:
            assert (await http.get("/temporal/")).status_code == 502
