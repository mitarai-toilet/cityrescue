import asyncio
import json
from pathlib import Path

from backend.app import app


def test_health_returns_ok():
    async def asgi_request():
        sent = []
        received = False

        async def receive():
            nonlocal received
            if not received:
                received = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"},
            "http_version": "1.1", "method": "GET", "scheme": "http",
            "path": "/health", "raw_path": b"/health", "query_string": b"",
            "root_path": "", "headers": [(b"host", b"test")],
            "client": ("127.0.0.1", 12345), "server": ("test", 80),
        }
        await asyncio.wait_for(app(scope, receive, send), timeout=3)
        start = next(m for m in sent if m["type"] == "http.response.start")
        body = next(m for m in sent if m["type"] == "http.response.body")["body"]
        return start["status"], json.loads(body)

    status, body = asyncio.run(asgi_request())
    assert status == 200
    assert body["status"] == "ok"
    assert body["service"] == "cityrescue-api"
