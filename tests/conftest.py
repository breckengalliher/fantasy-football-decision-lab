"""Task 2 local test boundary; never use a connected account or email service."""
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest
import requests

# AppTest allocates a shared temporary directory at import/collection time.
TEST_TEMP = Path(__file__).resolve().parents[1] / "work" / "test-runtime-temp"
TEST_TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEST_TEMP)


@pytest.fixture(autouse=True)
def local_auth_test_boundary(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("Local auth tests prohibit network and subprocess execution")
    # Windows asyncio implements its internal wake-up pipe over loopback.
    # Keep that local primitive available; HTTP provider requests remain blocked.
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    def local_connect(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect(sock, address)
        return forbidden()
    def local_connect_ex(sock, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return original_connect_ex(sock, address)
        return forbidden()
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(subprocess, "Popen", type("ForbiddenPopen", (subprocess.Popen,), {"__init__": forbidden}))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    for name in ("SDL_RESTRICTED_PILOT", "SDL_PILOT_PREPROVISIONED_ONLY", "SDL_PILOT_ACCOUNT_IDS", "SNAPSHOT_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
