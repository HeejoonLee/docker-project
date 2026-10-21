"""Reverse proxy for the Temporal Web UI, served under /temporal/ on the web app's port.

The Temporal UI runs with its public path set to /temporal, so paths are forwarded
unchanged. See docs/adr/0005-temporal-ui-behind-stonepedia.md.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

PREFIX = "/temporal"

# Hop-by-hop headers (RFC 9110 §7.6.1) are never forwarded.
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
       "transfer-encoding", "upgrade"}

router = APIRouter(include_in_schema=False)


@router.get(PREFIX)
async def _bare() -> RedirectResponse:
    return RedirectResponse(f"{PREFIX}/")


@router.api_route(PREFIX + "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def proxy(path: str, request: Request) -> Response:
    client: httpx.AsyncClient = request.app.state.temporal_ui
    headers = [(k, v) for k, v in request.headers.items() if k.lower() not in HOP | {"host", "content-length"}]
    upstream = client.build_request(
        request.method,
        f"{PREFIX}/{path}",
        params=request.query_params.multi_items(),
        headers=headers,
        content=await request.body(),
    )
    try:
        resp = await client.send(upstream, stream=True)
    except httpx.HTTPError as err:
        return Response(f"Temporal UI unreachable at {client.base_url}: {err}", status_code=502, media_type="text/plain")
    out = [(k, v) for k, v in resp.headers.multi_items() if k.lower() not in HOP]
    base = str(client.base_url).rstrip("/")
    out = [(k, v.replace(base, "", 1) if k.lower() == "location" and v.startswith(base) else v) for k, v in out]
    response = StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, background=BackgroundTask(resp.aclose))
    response.raw_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in out]
    return response
