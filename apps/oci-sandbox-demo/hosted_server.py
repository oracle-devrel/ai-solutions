"""OCI Hosted Deployment entrypoint for the Streamlit application.

OCI requires JSON readiness and liveness endpoints at ``/ready`` and
``/health``. Streamlit exposes its own health endpoint but does not offer
those routes, so this small reverse proxy reserves port 8080 for OCI and runs
Streamlit privately on port 8501.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from contextlib import suppress

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


UPSTREAM = "http://127.0.0.1:8501"
HOP_BY_HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


def forwarded_headers(request: web.Request) -> dict[str, str]:
    """Pass request headers through while leaving connection handling to aiohttp."""
    return {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "content-length"}
    }


async def streamlit_ready(app: web.Application) -> bool:
    try:
        async with app["client"].get(f"{UPSTREAM}/_stcore/health", timeout=ClientTimeout(total=1)) as response:
            return response.status == 200
    except Exception:
        return False


async def health(request: web.Request) -> web.Response:
    ready = await streamlit_ready(request.app)
    return web.json_response({"status": "ok" if ready else "starting"}, status=200 if ready else 503)


async def proxy_websocket(request: web.Request) -> web.StreamResponse:
    target = f"ws://127.0.0.1:8501{request.rel_url}"
    browser_socket = web.WebSocketResponse()
    await browser_socket.prepare(request)
    async with request.app["client"].ws_connect(target, headers=forwarded_headers(request)) as streamlit_socket:
        async def browser_to_streamlit() -> None:
            async for message in browser_socket:
                if message.type == WSMsgType.TEXT:
                    await streamlit_socket.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    await streamlit_socket.send_bytes(message.data)
                elif message.type == WSMsgType.ERROR:
                    break

        async def streamlit_to_browser() -> None:
            async for message in streamlit_socket:
                if message.type == WSMsgType.TEXT:
                    await browser_socket.send_str(message.data)
                elif message.type == WSMsgType.BINARY:
                    await browser_socket.send_bytes(message.data)
                elif message.type == WSMsgType.ERROR:
                    break

        await asyncio.gather(browser_to_streamlit(), streamlit_to_browser())
    return browser_socket


async def proxy(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await proxy_websocket(request)

    target = f"{UPSTREAM}{request.rel_url}"
    async with request.app["client"].request(
        request.method,
        target,
        headers=forwarded_headers(request),
        data=request.content,
        allow_redirects=False,
    ) as upstream_response:
        response = web.StreamResponse(status=upstream_response.status, headers={
            name: value for name, value in upstream_response.headers.items() if name.lower() not in HOP_BY_HOP_HEADERS
        })
        await response.prepare(request)
        async for chunk in upstream_response.content.iter_chunked(64 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


async def start_streamlit(app: web.Application) -> None:
    app["client"] = ClientSession(auto_decompress=False)
    app["streamlit"] = subprocess.Popen(
        [sys.executable, "run.py", "--server.address=127.0.0.1", "--server.port=8501", "--server.headless=true"],
        env=os.environ.copy(),
    )


async def stop_streamlit(app: web.Application) -> None:
    process: subprocess.Popen[bytes] = app["streamlit"]
    if process.poll() is None:
        process.send_signal(signal.SIGTERM)
        with suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
    await app["client"].close()


def main() -> None:
    app = web.Application()
    app.on_startup.append(start_streamlit)
    app.on_cleanup.append(stop_streamlit)
    app.router.add_get("/health", health)
    app.router.add_get("/ready", health)
    app.router.add_route("*", "/{path_info:.*}", proxy)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))


if __name__ == "__main__":
    main()
