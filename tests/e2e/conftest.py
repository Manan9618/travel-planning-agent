"""Session-scoped fixtures that launch a real backend + real frontend for the
Week 17 E2E suite: a real browser (pytest-playwright) drives the real React
build over real HTTP/WebSocket against a real `uvicorn` process running the
stub-tool-backed app from `stub_backend.py`. Ports are deliberately different
from the normal dev setup (8000/5173) so this suite can run alongside a
developer's own `make serve`/`make frontend-dev` without colliding.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"

BACKEND_PORT = 8811
FRONTEND_PORT = 5811
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
# Vite's dev server (no --host flag) binds only the IPv6 loopback for
# "localhost" resolution, unlike uvicorn's IPv4-only default above - found
# by 127.0.0.1 connection-refused-ing here while localhost worked.
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

_STARTUP_TIMEOUT_SECONDS = 60


def _wait_until_up(url: str, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            requests.get(url, timeout=2)
            return
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"{url} did not come up within {timeout}s") from last_error


@pytest.fixture(scope="session")
def backend_server():
    proc = subprocess.Popen(
        [
            "poetry",
            "run",
            "uvicorn",
            "tests.e2e.stub_backend:app",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            # `tests.e2e.stub_backend` resolves fine from cwd (repo root), but
            # its own `from travel_agent...` imports need `src/` on the path
            # too - the same fix `make serve` needed (plain uvicorn has no
            # equivalent of pytest's `pythonpath` ini option).
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "CORS_ORIGINS": f"{FRONTEND_URL},http://localhost:{FRONTEND_PORT}",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_up(f"{BACKEND_URL}/docs", _STARTUP_TIMEOUT_SECONDS)
        yield BACKEND_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def frontend_server(backend_server):
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort"],
        cwd=FRONTEND_DIR,
        env={**os.environ, "VITE_API_BASE_URL": backend_server},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_up(FRONTEND_URL, _STARTUP_TIMEOUT_SECONDS)
        yield FRONTEND_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def app_url(frontend_server):
    return frontend_server
