"""API proxy — SHIPPED BY THE PLATFORM. DO NOT MODIFY OR RECREATE THIS FILE.

The browser calls same-origin /api/<slug>/<path> (or /tip-api/<path> for the
built-in TIP connection); this router resolves the connection, attaches its auth
server-side, forwards the request, and streams the upstream response back verbatim.
"""
import requests
from fastapi import APIRouter, Request, Response

from connections import inject_auth, load_connections, resolve_secret

router = APIRouter()

# Hop-by-hop / recomputed headers we must not forward as-is. Dropping
# accept-encoding means the upstream returns an uncompressed body, so streaming
# bytes back with the upstream Content-Type is always consistent for the browser.
_DROP_HEADERS = {"host", "content-length", "connection", "accept-encoding"}
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def _forward(slug: str, path: str, request: Request, body: bytes) -> Response:
    conn = load_connections().get(slug)
    if conn is None:
        return Response(
            content=b'{"status": false, "message": "unknown_connection"}',
            status_code=404, media_type="application/json",
        )
    base = (conn.get("base_url", "") or "").rstrip("/")
    url = f"{base}/{path.lstrip('/')}"

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _DROP_HEADERS}
    params = dict(request.query_params)
    inject_auth(conn, headers, params, resolve_secret(conn))

    try:
        upstream = requests.request(
            method=request.method, url=url, params=params, data=body,
            headers=headers, timeout=60,
        )
    except requests.RequestException:
        return Response(
            content=b'{"status": false, "message": "proxy_error"}',
            status_code=502, media_type="application/json",
        )

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("Content-Type", "application/json"),
    )


@router.api_route("/api/{slug}/{path:path}", methods=_METHODS)
async def api_proxy(slug: str, path: str, request: Request) -> Response:
    return _forward(slug, path, request, await request.body())


@router.api_route("/tip-api/{path:path}", methods=_METHODS)
async def tip_api_proxy(path: str, request: Request) -> Response:
    return _forward("tip", path, request, await request.body())
