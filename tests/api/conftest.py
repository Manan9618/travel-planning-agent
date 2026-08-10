"""Shared fixtures for the Week 15 FastAPI test suite.

Mirrors tests/integration/test_planning_graph.py's stub-tool pattern (real
graph wiring/routing, but every external API replaced with a deterministic
in-memory stub) so these tests stay fast and offline, and additionally
disables map-thumbnail rasterization (`render_pdf_map_thumbnail=False`) for
the same reason Week 13/14's own graph tests do: no real headless-browser
launch per test.

Known residual flakiness: running this file's ~40 tests (each spinning up
its own TestClient portal — a background thread + event loop + thread-pool
executor — to drive a full graph run) occasionally segfaults the whole
pytest process, roughly 1 run in 5-8. Investigated at length: it is NOT the
two real bugs this suite caught and fixed (real Redis/Google Maps calls
from an un-stubbed TravelTimeEstimator, and dangling background tasks still
mid-write when a test's portal tore down — both fixed below), and it
persists after upgrading Python 3.11.0 -> 3.11.14. Crash sites vary randomly
across unrelated native code (redis-py, sqlite3, WeasyPrint's layout
engine) between runs, which points to memory corruption from heavy,
artificial thread-pool churn (dozens of portals created/destroyed in rapid
succession within one process) rather than a bug in any one library or in
this project's own code. The real server, driven by an actual uvicorn
process handling real HTTP/WebSocket traffic (see the Week 15 README entry
for the live test), showed no such issue under repeated exercise. If this
resurfaces and needs a full fix rather than a documented residual risk, the
next lever to try is consolidating the tests that need a custom parser/
narrator onto fewer, shared portals (attempted once already here — it cut
churn but introduced shared rate-limiter/session-store state across tests,
so it was reverted rather than shipped half-fixed).
"""

from __future__ import annotations

import contextlib
import time

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver

from travel_agent.agents.graph import build_planning_graph
from travel_agent.agents.state import determine_valid_steps
from travel_agent.api.app import create_app
from travel_agent.api.sessions import SessionStore
from travel_agent.api.users import UserStore
from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Restaurant,
    TravelPreferences,
)
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.conflict_resolver import ConflictResolver
from travel_agent.tools.multi_day_optimizer import MultiDayOptimizer
from travel_agent.tools.pdf_generator import PDFGenerator


class FixedTravelTime:
    """No-network stand-in for TravelTimeEstimator (same double
    test_planning_graph.py uses) — without this, MultiDayOptimizer's default
    constructor reaches for a real TravelTimeEstimator/Cache, which opens a
    real Redis connection and calls the real Google Maps API on every
    build_itinerary step. Forgetting it here (unlike test_planning_graph.py,
    which injects it correctly) is what silently made this whole test suite
    non-offline, and a burst of concurrent real Redis connections opened by
    dozens of rapid test runs is what triggered a genuine segfault deep in
    the redis-py client during full-suite runs."""

    def minutes_between(self, olat, olng, dlat, dlng, mode="driving"):
        return 15


class FixedDistanceMatrix:
    """Same no-network rationale as FixedTravelTime, for MultiDayOptimizer's
    separate DistanceMatrixTool (used for clustering/route-ordering)."""

    def compute_matrix(self, points, mode="driving"):
        n = len(points)
        return [[0 if i == j else 15 for j in range(n)] for i in range(n)]


class DeterministicSupervisor:
    def decide_next(self, state):
        return determine_valid_steps(state)[0]


class StubParser:
    """budget_total=2000 comfortably covers fixed costs (flight 650 + hotel
    100/night); pass a lower one to force an unresolvable budget conflict
    and exercise the human-in-the-loop pause."""

    def __init__(self, **overrides):
        self._overrides = overrides

    def parse(self, text, reference_date=None):
        defaults = dict(
            origin="Boston",
            destination="Paris",
            start_date="2026-09-01",
            end_date="2026-09-03",
            budget_total=2000,
            raw_text=text,
        )
        defaults.update(self._overrides)
        return TravelPreferences(**defaults)

    def parse_partial(self, text, reference_date=None):
        # Mirrors a real refinement parse that only reports what it's
        # confident changed — no destination/dates unless a test explicitly
        # passes them via overrides, so /refine's merge-over-existing-prefs
        # behavior gets genuinely exercised rather than just re-asserting
        # fixed defaults.
        return dict(self._overrides)


class FailingParser:
    def parse(self, text, reference_date=None):
        raise RuntimeError("parser boom")

    def parse_partial(self, text, reference_date=None):
        raise RuntimeError("parser boom")


class StubFlightTool:
    def search(self, *args, **kwargs):
        return [
            FlightOption(
                airline="AF",
                origin="BOS",
                destination="PAR",
                departure_time="2026-09-01T02:00:00",
                arrival_time="2026-09-01T14:00:00",
                duration_minutes=420,
                price=650,
            )
        ]


class StubHotelTool:
    def search(self, *args, **kwargs):
        return [
            HotelOption(
                name="Test Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100
            )
        ]


class StubAttractionTool:
    def search(self, *args, **kwargs):
        return [Attraction(name="Louvre", lat=48.86, lng=2.33, rating=4.5)]


class StubRestaurantTool:
    def search(self, *args, **kwargs):
        return [Restaurant(name="Cafe", lat=48.85, lng=2.35, rating=4.0)]


class StubWeatherTool:
    def get_forecast(self, *args, **kwargs):
        return []


class StubPhotoTool:
    """No-op stand-in for UnsplashPhotoTool. Without this, a real
    UNSPLASH_ACCESS_KEY in the environment would make these offline tests
    hit the real Unsplash API on every enrich_attractions/generate_pdf
    step, the same offline-safety rationale as FixedTravelTime above."""

    def get_cover_photo(self, destination):
        return None

    def get_photo(self, query, thumbnail=False):
        return None


class StubDescriptionTool:
    """No-op stand-in for AttractionDescriberTool, for the same reason
    StubPhotoTool exists: without it, a real OPENAI_API_KEY means these
    offline tests would make a real LLM call on every enrich_attractions
    step."""

    def describe(self, titles, destination):
        return {}


class FakeNarrator:
    def __init__(self, tokens=None, fail=False):
        self._tokens = tokens if tokens is not None else ["Bon", " voyage", "!"]
        self._fail = fail

    async def narrate(self, itinerary):
        if self._fail:
            raise RuntimeError("narration boom")
        for token in self._tokens:
            yield token


def build_stub_graph(
    parser=None,
    flight_tool=None,
    hotel_tool=None,
    attraction_tool=None,
    restaurant_tool=None,
    weather_tool=None,
):
    # MemorySaver, not SqliteSaver: these tests run many full graph
    # invocations back-to-back, and that density reliably surfaced a real
    # upstream race in SqliteSaver's internal background-write thread pool
    # (a segfault-level crash, reproduced independently of anything in this
    # project's own code — see the Week 15 README entry). MemorySaver is a
    # plain in-memory dict with no background threading, sidestepping it
    # entirely; it's a fully supported LangGraph checkpointer, just not the
    # persistent one `create_app()`'s production default uses.
    return build_planning_graph(
        parser=parser or StubParser(),
        flight_tool=flight_tool or StubFlightTool(),
        hotel_tool=hotel_tool or StubHotelTool(),
        attraction_tool=attraction_tool or StubAttractionTool(),
        restaurant_tool=restaurant_tool or StubRestaurantTool(),
        weather_tool=weather_tool or StubWeatherTool(),
        itinerary_builder=MultiDayOptimizer(
            travel_time_estimator=FixedTravelTime(), distance_matrix_tool=FixedDistanceMatrix()
        ),
        photo_tool=StubPhotoTool(),
        description_tool=StubDescriptionTool(),
        conflict_detector=ConflictDetector(travel_time_estimator=FixedTravelTime()),
        conflict_resolver=ConflictResolver(travel_time_estimator=FixedTravelTime()),
        pdf_generator=PDFGenerator(photo_tool=StubPhotoTool()),
        supervisor=DeterministicSupervisor(),
        render_pdf_map_thumbnail=False,
        checkpointer=MemorySaver(),
    )


@pytest.fixture
def app_factory():
    """A callable that builds a fresh, fully-isolated app per call, so tests
    that need custom parser/narrator/search-tool behavior aren't stuck with
    fixture defaults (e.g. Week 21's incremental-refinement tests, which need
    to count how many times each search tool was actually called)."""

    def _make(parser=None, narrator=None, **tool_overrides):
        graph = build_stub_graph(parser=parser, **tool_overrides)
        return create_app(
            graph=graph,
            session_store=SessionStore(":memory:"),
            user_store=UserStore(":memory:"),
            narrator=narrator or FakeNarrator(),
            parser=parser or StubParser(),
        )

    return _make


DEFAULT_TEST_EMAIL = "traveler@example.com"
DEFAULT_TEST_PASSWORD = "hunter2222"  # noqa: S105 - test fixture, not a real credential


def register_and_authenticate(
    test_client: TestClient, email: str = DEFAULT_TEST_EMAIL, password: str = DEFAULT_TEST_PASSWORD
) -> str:
    """Registers a fresh account against `test_client`'s own (isolated,
    in-memory) UserStore and sets the resulting bearer token as a default
    header on the client, so every request this client makes from here on
    is already authenticated as that user — every /plan, /refine, /export,
    etc. test needs real user accounts (added alongside login/register) to
    get past `get_current_user` at all, and updating every individual test
    body to register+attach a token itself would be a lot of repetition for
    something that's really a fixture concern. Returns the raw token too,
    for the handful of tests (WebSocket) that need it as `?token=...` since
    a browser WebSocket can't send a custom Authorization header."""
    resp = test_client.post("/auth/register", json={"email": email, "password": password})
    token = resp.json()["access_token"]
    test_client.headers["Authorization"] = f"Bearer {token}"
    return token


def drain_all_sessions(test_client: TestClient, timeout: float = 5.0) -> None:
    """Waits for every session created during a test to reach a terminal
    state before its TestClient's `with` block is allowed to exit.

    Without this, a test that doesn't itself wait for completion (e.g. one
    that only checks the immediate 202 response, or a rate-limit test firing
    a dozen requests without caring how they finish) can leave a background
    `/plan` task genuinely still running — including mid-write inside
    SessionStore's own SQLite connection, on its own thread — at the exact
    moment TestClient's portal (the thread + event loop backing every
    request) gets torn down. That reliably segfaulted the whole pytest
    process during full-suite runs; this makes sure nothing is left
    in-flight when a test's client goes out of scope.
    """
    session_store = test_client.app.state.session_store
    pending = set(session_store.list_ids())
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        pending = {
            sid
            for sid in pending
            if session_store.get(sid).status not in ("completed", "failed", "awaiting_review")
        }
        if pending:
            time.sleep(0.05)


@contextlib.contextmanager
def isolated_client(app):
    """Same lifecycle guarantee as the `client` fixture below, for tests that
    need their own custom app (a different parser/narrator) and so build
    their own TestClient directly instead of using the fixture."""
    with TestClient(app) as test_client:
        test_client.auth_token = register_and_authenticate(test_client)
        yield test_client
        drain_all_sessions(test_client)


@pytest.fixture
def client(app_factory):
    # Must be entered as a context manager: TestClient only keeps its portal
    # (the background thread + event loop that requests run on) alive for
    # the lifetime of the `with` block. Without it, each request spins up a
    # transient loop that's torn down right after — any `asyncio.create_task`
    # background work (like a /plan run) gets abandoned mid-flight instead of
    # continuing to make progress between polling calls.
    with TestClient(app_factory()) as test_client:
        test_client.auth_token = register_and_authenticate(test_client)
        yield test_client
        drain_all_sessions(test_client)


def wait_until_terminal(client: TestClient, session_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    data: dict = {}
    while time.time() < deadline:
        data = client.get(f"/plan/{session_id}").json()
        if data["status"] in ("completed", "failed", "awaiting_review"):
            return data
        time.sleep(0.05)
    raise TimeoutError(f"session {session_id} never reached a terminal state: {data}")
