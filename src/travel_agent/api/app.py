"""FastAPI backend — Week 15 deliverable.

Exposes the LangGraph planning pipeline (Weeks 1-14) over HTTP + WebSocket:

- `POST /plan` starts a new planning run in the background and returns
  immediately (202 — see "async processing" below); `GET /plan/{session_id}`
  polls status/results.
- `POST /plan/{session_id}/resume` continues a run paused at Week 6's
  human-in-the-loop conflict-review step.
- `POST /refine` starts a NEW session seeded from the old one's preferences
  merged with a refinement request, still under a fresh `session_id` (this
  sidesteps a real LangGraph gotcha: `PlanningState.completed_steps` uses
  an additive `operator.add` reducer, so feeding a shorter list into an
  *existing* thread_id would concatenate rather than reset it) — but as of
  Week 21, it's an incremental edit, not a full re-plan: only the search
  steps whose actual inputs changed (see `agents/refinement.py`) run for
  real; every other already-completed search result is carried over into
  the new thread's seed state as-is, so a refinement that doesn't touch
  origin/destination/dates/travelers/budget/interests skips flights,
  hotels, attractions, restaurants, and weather entirely — no re-hitting
  those external, often rate-limited APIs for a change they have nothing
  to do with. Itinerary assembly onward always reruns.
- `GET /export/{session_id}/pdf` and `/map` serve Week 14/13's generated
  artifacts.
- `WS /ws/{session_id}` streams step-progress events plus a genuine
  token-by-token LLM narration (`ItineraryNarrator`) once the itinerary is
  built — see `sessions.py` for why this polls the SQLite event log
  underneath rather than needing a separate in-memory pub/sub layer.

Async processing: every planning run (`/plan`, `/refine`, `/resume`) is
kicked off as an `asyncio.create_task` and the endpoint returns immediately;
`GET /plan/{session_id}` is the polling endpoint for status and results.

`create_app()` takes every collaborator as an optional override (same DI
pattern as every tool/node in this project) so tests can swap in a fully
stubbed graph — no `app = create_app()` module-level singleton is defined
here on purpose: building the default app touches the filesystem (SQLite
checkpoint + session-store files); production entrypoints should use
uvicorn's `--factory` flag (`uvicorn travel_agent.api.app:create_app
--factory`) so that only happens when the server actually starts, not on
every import (e.g. during test collection).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from travel_agent.agents.graph import (
    build_planning_graph,
    build_postgres_checkpointer,
    build_sqlite_checkpointer,
)
from travel_agent.agents.refinement import SEARCH_STEP_STATE_FIELD, build_refinement_seed
from travel_agent.api.schemas import (
    PlanRequest,
    PlanResponse,
    RefineRequest,
    ResumeRequest,
    SessionStateResponse,
)
from travel_agent.api.sessions import PostgresSessionStore, SessionStore, build_session_store
from travel_agent.config import settings
from travel_agent.models.core import Itinerary
from travel_agent.observability.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
)
from travel_agent.observability.metrics import PLANNING_DURATION
from travel_agent.observability.sentry import init_sentry
from travel_agent.tools.itinerary_narrator import ItineraryNarrator
from travel_agent.tools.preference_parser import PreferenceParser

logger = logging.getLogger(__name__)

WS_POLL_INTERVAL_SECONDS = 0.2
TERMINAL_EVENT_TYPES = {"done", "error", "awaiting_review"}
PLAN_RATE_LIMIT = "10/minute"


def verify_api_key(request: Request) -> None:
    if not settings.api_key:
        return  # no key configured -> auth disabled (local/dev default)
    if request.headers.get("X-API-Key") != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def create_app(
    graph: CompiledStateGraph | None = None,
    session_store: SessionStore | PostgresSessionStore | None = None,
    narrator: ItineraryNarrator | None = None,
    parser: PreferenceParser | None = None,
) -> FastAPI:
    # Called here, not at module import time, for the same reason
    # build_planning_graph()/SessionStore() aren't module-level singletons
    # (see the module docstring): a bare `import travel_agent.api.app`
    # (e.g. during test collection) shouldn't have side effects -
    # configure_logging is idempotent (a no-op past the first real call)
    # and init_sentry is a no-op without SENTRY_DSN, so calling both once
    # per create_app() is cheap and safe even across many test-suite calls.
    configure_logging(level=settings.log_level, json_format=settings.log_format == "json")
    init_sentry(settings.sentry_dsn)
    # LangSmith needs no wiring here at all - LangChain/LangGraph read
    # LANGCHAIN_TRACING_V2/LANGCHAIN_API_KEY/LANGCHAIN_PROJECT straight out
    # of the environment (already populated by config.py's load_dotenv()).
    # This line only makes what's active visible at a glance in the logs.
    logger.info(
        "observability configured: langsmith=%s sentry=%s database=%s",
        settings.langsmith_enabled,
        bool(settings.sentry_dsn),
        "postgres" if settings.database_url else "sqlite",
    )

    # Postgres (Week 18's Docker Compose) when DATABASE_URL is set, SQLite
    # otherwise (plain `make serve`, unchanged from Weeks 4/15) - both the
    # checkpointer and the session store switch together, the same
    # degrades-gracefully-without-real-infra pattern Redis caching uses
    # everywhere else in this project.
    graph = graph or build_planning_graph(
        checkpointer=(
            build_postgres_checkpointer(settings.database_url)
            if settings.database_url
            else build_sqlite_checkpointer()
        )
    )
    session_store = session_store or build_session_store(settings.database_url)
    narrator = narrator or ItineraryNarrator()
    parser = parser or PreferenceParser()

    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI(
        title="Autonomous AI Travel Planning Agent",
        version="0.1.0",
        description=(
            "Turns a natural-language travel request into a complete, optimized "
            "day-by-day itinerary — real flights, hotels, attractions, restaurants, "
            "weather-aware scheduling, budget optimization, an interactive map, and "
            "a PDF export, orchestrated by a LangGraph agent. Start with `POST /plan`, "
            "then either poll `GET /plan/{session_id}` or connect to "
            "`WS /ws/{session_id}` for live progress and token-streamed narration. "
            "See the [README](https://github.com/Manan9618/travel-planning-agent) "
            "for the full 24-week build log and architecture."
        ),
    )
    app.state.limiter = limiter
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.session_store = (
        session_store  # exposed for tests to drain background work on teardown
    )
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        # Correlation ID (Week 19) for every request's own logs - separate
        # from _drive_graph's session_id binding below, which covers a
        # background planning run that outlives this request/response cycle
        # entirely (POST /plan returns 202 long before the graph finishes).
        request_id = str(uuid.uuid4())
        bind_request_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_request_context()
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get(
        "/metrics",
        tags=["observability"],
        summary="Prometheus metrics",
        description="Raw Prometheus exposition format — planning_step_calls_total, "
        "planning_duration_seconds, llm_tokens_total, llm_cost_usd_total, and more "
        "(see observability/metrics.py). Not authenticated; not meant for browsers.",
    )
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    def _config(session_id: str) -> dict:
        # LangGraph's default recursion_limit (25) counts each worker-step ->
        # supervisor round trip as 2 ticks; with 12 worker steps (as of the
        # enrich_attractions addition) plus one final DONE-only supervisor
        # tick, a full run needs exactly 25 - the default leaves zero
        # headroom and a genuinely failing run (retried steps, extra
        # human-review round trips) would hit GraphRecursionError instead of
        # finishing or erroring cleanly. Set generously above that.
        return {"configurable": {"thread_id": session_id}, "recursion_limit": 100}

    def _state_response(session_id: str) -> SessionStateResponse:
        record = session_store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        values = graph.get_state(_config(session_id)).values or {}
        return SessionStateResponse(
            session_id=session_id,
            status=record.status,
            completed_steps=values.get("completed_steps", []),
            errors=values.get("errors", []),
            preferences=values.get("preferences"),
            itinerary=values.get("itinerary"),
            conflict_log=values.get("conflict_log", []),
            unresolved_conflicts=values.get("unresolved_conflicts", []),
            budget_evaluation=values.get("budget_evaluation"),
            pdf_path=values.get("pdf_path"),
            map_html_available=bool(values.get("map_html")),
        )

    async def _narrate_if_possible(session_id: str, values: dict) -> None:
        itinerary_data = values.get("itinerary")
        if not itinerary_data:
            return
        try:
            itinerary = Itinerary(**itinerary_data)
            async for token in narrator.narrate(itinerary):
                session_store.append_event(session_id, "narration_token", {"token": token})
        except Exception as exc:
            logger.warning("narration failed for %s: %s", session_id, exc)

    async def _drive_graph(session_id: str, graph_input) -> None:
        """Runs the graph to completion or an interrupt, then narrates and
        marks the session done/awaiting-review/failed. Shared by /plan,
        /refine, and /resume.

        Deliberately runs the EXISTING, already-tested sync `graph.stream()`
        (same node-execution machinery used unchanged since Week 4) inside a
        single background thread via `asyncio.to_thread`, rather than
        switching to LangGraph's async `.astream()` API: that would require
        an async-compatible checkpointer, and the current
        `langgraph-checkpoint-sqlite` release has a real upstream bug
        (`AsyncSqliteSaver` calls `conn.is_alive()`, which newer `aiosqlite`
        releases removed) that only an unrelated major-version bump would
        fix — too large/risky a change for this week.

        Recording progress by polling `graph.get_state()` from the event
        loop *while* `graph.invoke()` ran concurrently in another thread was
        the first thing tried here — it reliably hung, because both threads
        end up touching the same raw sqlite3 checkpointer connection at the
        same time (SQLite doesn't support that even with
        `check_same_thread=False`, which only disables Python's own
        same-thread assertion, not real concurrent access). Consuming
        `graph.stream()`'s per-node chunks *inside* the one background
        thread instead means only that thread ever touches the checkpointer
        while the graph is running — the event loop only reads
        `graph.get_state()` afterward, once the thread has finished.
        """
        config = _config(session_id)

        def _run_and_record_steps() -> None:
            for chunk in graph.stream(graph_input, config=config):
                for node_name, output in chunk.items():
                    # "supervisor" just picks the next step, nothing to report.
                    # "__interrupt__" is LangGraph's own special key when the
                    # graph pauses (Week 6's human_review) — its value is a
                    # tuple of Interrupt objects, not a node's output dict, so
                    # it doesn't have an .get() to call.
                    if node_name in ("supervisor", "__interrupt__"):
                        continue
                    session_store.append_event(
                        session_id,
                        "step_completed",
                        {"step": node_name, "errors": output.get("errors", [])},
                    )

        # session_id (Week 19 correlation ID): bound for this whole
        # background task's lifetime, not just the initial request/response
        # cycle (add_request_id's request_id above is already long gone by
        # the time this finishes) - every log line from every node this run
        # touches, even deep in nodes.py, carries it (contextvars propagate
        # into asyncio.to_thread's worker thread per its own guarantee).
        bind_request_context(session_id=session_id)
        start = time.monotonic()
        try:
            await asyncio.to_thread(_run_and_record_steps)
            state = graph.get_state(config)
            if state.next:
                session_store.update_status(session_id, "awaiting_review")
                session_store.append_event(
                    session_id, "awaiting_review", {"next": list(state.next)}
                )
                return
            await _narrate_if_possible(session_id, state.values)
            session_store.update_status(session_id, "completed")
            session_store.append_event(session_id, "done", {})
        except Exception as exc:
            logger.exception("plan execution failed for %s", session_id)
            session_store.update_status(session_id, "failed")
            session_store.append_event(session_id, "error", {"message": str(exc)})
        finally:
            PLANNING_DURATION.observe(time.monotonic() - start)
            clear_request_context()

    @app.post(
        "/plan",
        response_model=PlanResponse,
        status_code=202,
        dependencies=[Depends(verify_api_key)],
        tags=["planning"],
        summary="Start a new planning run",
        description=(
            "Starts planning a brand-new trip in the background and returns "
            "immediately with a session_id. The actual work (parsing preferences, "
            "searching flights/hotels/attractions/restaurants/weather in parallel, "
            "building and optimizing the itinerary, generating the map and PDF) "
            "continues asynchronously — poll `GET /plan/{session_id}` or stream "
            "progress via `WS /ws/{session_id}`."
        ),
    )
    @limiter.limit(PLAN_RATE_LIMIT)
    async def plan(request: Request, body: PlanRequest) -> PlanResponse:
        session_id = str(uuid.uuid4())
        session_store.create(session_id, body.raw_text)
        asyncio.create_task(
            _drive_graph(
                session_id, {"raw_text": body.raw_text, "errors": [], "completed_steps": []}
            )
        )
        return PlanResponse(session_id=session_id, status="running")

    @app.get(
        "/plan/{session_id}",
        response_model=SessionStateResponse,
        dependencies=[Depends(verify_api_key)],
        tags=["planning"],
        summary="Poll a session's current state",
        description="Returns the current status, completed steps, and any results "
        "available so far (preferences, itinerary, budget evaluation, ...) for a "
        "session started by /plan or /refine. Safe to poll repeatedly.",
    )
    async def get_plan(session_id: str) -> SessionStateResponse:
        return _state_response(session_id)

    @app.post(
        "/plan/{session_id}/resume",
        response_model=PlanResponse,
        dependencies=[Depends(verify_api_key)],
        tags=["planning"],
        summary="Resume a session paused for human review",
        description="Continues a session whose status is awaiting_review (an "
        "unresolved budget or scheduling conflict — see the awaiting_review "
        "WebSocket event for details) with the traveler's approve/reject decision.",
    )
    async def resume_plan(session_id: str, body: ResumeRequest) -> PlanResponse:
        if session_store.get(session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        session_store.update_status(session_id, "running")
        asyncio.create_task(_drive_graph(session_id, Command(resume={"approved": body.approved})))
        return PlanResponse(session_id=session_id, status="running")

    @app.post(
        "/refine",
        response_model=PlanResponse,
        status_code=202,
        dependencies=[Depends(verify_api_key)],
        tags=["planning"],
        summary="Refine an existing trip with a follow-up request",
        description=(
            "Starts a new session seeded from an existing (completed or "
            "awaiting-review) session's results, merged with a natural-language "
            "refinement. As of Week 21, only the search steps whose actual inputs "
            "changed (destination, dates, origin, travelers, budget, interests) "
            "re-run against real APIs — unaffected results (e.g. flights, when only "
            "interests changed) are carried over rather than re-fetched. Watch for "
            "the `refinement_seeded` WebSocket event to see which steps were reused."
        ),
    )
    @limiter.limit(PLAN_RATE_LIMIT)
    async def refine(request: Request, body: RefineRequest) -> PlanResponse:
        if session_store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        existing_state = graph.get_state(_config(body.session_id)).values or {}
        existing_prefs = existing_state.get("preferences") or {}

        # parse_partial(), not parse(): a refinement like "more outdoor activities"
        # mentions no destination at all, and parse() requires one (correctly, for a
        # brand-new /plan request). parse_partial() tolerates that and returns only
        # what the LLM was confident about, to overlay onto the existing preferences
        # below rather than replace them outright.
        parsed = await asyncio.to_thread(parser.parse_partial, body.raw_text)
        updates = {
            k: v for k, v in parsed.items() if k != "raw_text" and v not in (None, [], {}, "")
        }
        merged_preferences = {**existing_prefs, **updates, "raw_text": body.raw_text}
        # Accumulating preference lists (interests, must-see, dietary, accessibility)
        # merge by union instead of replace — a refinement chip like "more outdoor
        # activities" should add to the trip's interests, not wipe out "art and
        # museums" from the original request.
        for list_field in (
            "interests",
            "must_see",
            "dietary_restrictions",
            "accessibility_needs",
        ):
            if list_field in updates:
                existing_list = existing_prefs.get(list_field) or []
                merged_preferences[list_field] = list(
                    dict.fromkeys([*existing_list, *updates[list_field]])
                )

        new_session_id = str(uuid.uuid4())
        session_store.create(new_session_id, body.raw_text, parent_session_id=body.session_id)
        seed = build_refinement_seed(body.raw_text, merged_preferences, existing_state, updates)
        reused = [
            step.value for step in SEARCH_STEP_STATE_FIELD if step.value in seed["completed_steps"]
        ]
        session_store.append_event(new_session_id, "refinement_seeded", {"reused_steps": reused})
        asyncio.create_task(_drive_graph(new_session_id, seed))
        return PlanResponse(session_id=new_session_id, status="running")

    @app.get(
        "/export/{session_id}/pdf",
        dependencies=[Depends(verify_api_key)],
        tags=["export"],
        summary="Download the generated PDF itinerary",
        description="Returns the PDF (cover page, day-by-day plan, map thumbnail, "
        "QR code to the interactive map, budget table) once generate_pdf has "
        "completed — 404 until then.",
        response_class=FileResponse,
    )
    async def export_pdf(session_id: str) -> FileResponse:
        pdf_path = (graph.get_state(_config(session_id)).values or {}).get("pdf_path")
        if not pdf_path or not Path(pdf_path).exists():
            raise HTTPException(status_code=404, detail="PDF not available for this session")
        return FileResponse(pdf_path, media_type="application/pdf", filename=Path(pdf_path).name)

    @app.get(
        "/export/{session_id}/map",
        dependencies=[Depends(verify_api_key)],
        tags=["export"],
        summary="View the interactive map",
        description="Returns a self-contained interactive HTML map (Folium/Leaflet, "
        "color-coded by day with a route-reveal timeline) once generate_map has "
        "completed — 404 until then.",
        response_class=HTMLResponse,
    )
    async def export_map(session_id: str) -> HTMLResponse:
        map_html = (graph.get_state(_config(session_id)).values or {}).get("map_html")
        if not map_html:
            raise HTTPException(status_code=404, detail="map not available for this session")
        return HTMLResponse(map_html)

    @app.websocket("/ws/{session_id}")
    async def ws_stream(websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        if session_store.get(session_id) is None:
            await websocket.send_json({"type": "error", "message": "session not found"})
            await websocket.close()
            return
        last_id = 0
        try:
            while True:
                for event in session_store.get_events(session_id, after_id=last_id):
                    await websocket.send_json({"type": event.event_type, **event.payload})
                    last_id = event.id
                    if event.event_type in TERMINAL_EVENT_TYPES:
                        await websocket.close()
                        return
                await asyncio.sleep(WS_POLL_INTERVAL_SECONDS)
        except WebSocketDisconnect:
            pass

    return app
