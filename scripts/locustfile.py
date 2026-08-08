"""Week 17 load test: verify the system handles 10 concurrent planning
sessions, per the plan's target.

Each simulated user submits one real POST /plan request and polls
GET /plan/{id} to completion, then stops (StopUser) - this is a single
concurrent *burst* of sessions, not sustained repeated hammering, matching
what the plan actually asks to be verified. Points at the stub-tool-backed
backend (tests/e2e/stub_backend.py) rather than the real one: what's under
test here is this project's own concurrency handling (the async background
task per session, the SQLite checkpointer under concurrent writes, the
rate-limit middleware), not third-party API behavior or its cost/rate limits.

Usage:
    poetry run uvicorn tests.e2e.stub_backend:app --port 8811   # one terminal
    make load-test                                               # another
"""

from __future__ import annotations

import itertools
import time

from locust import HttpUser, between, events, task
from locust.exception import StopUser

_REQUESTS = itertools.cycle(
    [
        "5 days in Paris, I love art and museums",
        "3 days in Tokyo, budget $1500",
        "7 days in New York, adventure trip",
        "4 days in Barcelona, honeymoon",
        "10 days in Bali, relaxed pace",
    ]
)

_POLL_INTERVAL_SECONDS = 1
_POLL_TIMEOUT_SECONDS = 60
_TERMINAL_STATUSES = {"completed", "failed", "awaiting_review"}


class PlanningUser(HttpUser):
    wait_time = between(0, 1)

    @task
    def plan_one_trip_to_completion(self):
        start = time.monotonic()
        raw_text = next(_REQUESTS)

        resp = self.client.post("/plan", json={"raw_text": raw_text}, name="/plan [start]")
        if resp.status_code != 202:
            raise StopUser()
        session_id = resp.json()["session_id"]

        status = None
        deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            poll = self.client.get(f"/plan/{session_id}", name="/plan/:id [poll]")
            status = poll.json().get("status")
            if status in _TERMINAL_STATUSES:
                break
            time.sleep(_POLL_INTERVAL_SECONDS)

        elapsed_ms = (time.monotonic() - start) * 1000
        events.request.fire(
            request_type="SESSION",
            name="full planning session",
            response_time=elapsed_ms,
            response_length=0,
            exception=None if status == "completed" else RuntimeError(f"ended as {status!r}"),
        )
        raise StopUser()
