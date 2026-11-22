"""Exercise the real ASGI app over HTTP with stdlib; no extra test dependency."""

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from ecg import report
from ecg.api import app


@pytest.fixture
def api_client(monkeypatch):
    calls = []

    def fake_explanation(payload):
        calls.append(payload)
        return {"explanation": {section: "Possible measured timing; clinician review is advised."
                                for section in ("Summary", "What the numbers mean", "Possible findings",
                                                "Limitations", "When to see a doctor")}, "error": None}

    monkeypatch.setattr(report, "explain_measurements", fake_explanation)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    address = f"http://127.0.0.1:{listener.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "Test API failed to start"

    def request(path, body=None, *, data=None, headers=None):
        request_headers = headers or {}
        if body is not None:
            data = json.dumps(body).encode()
            request_headers = {"Content-Type": "application/json", **request_headers}
        req = urllib.request.Request(address + path, data=data, headers=request_headers)
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    yield request, calls
    server.should_exit = True
    thread.join(timeout=5)
    listener.close()
    assert not thread.is_alive(), "Test API did not shut down"
