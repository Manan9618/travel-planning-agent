"""FastAPI backend — Week 15 deliverable.

Exposes the LangGraph planning pipeline (Weeks 1-14) over HTTP + WebSocket:

- `POST /plan` starts a new planning run in the background and returns
  immediately (202 — see "async processing" below); `GET /plan/{session_id}`
  polls status/results.
- `POST /plan/{session_id}/resume` continues a run paused at Week 6's
  human-in-the-loop conflict-review step.
- `POST /refine` starts a NEW session seeded from the old one's preferences
  merged with a refinement request — a full re-plan under a fresh
  `session_id` rather than an in-place edit. This sidesteps a real
  LangGraph gotcha: `PlanningState.completed_steps` uses an additive
  (`operator.add`) reducer, so feeding a shorter `completed_steps` list into
  an *existing* thread_id would concatenate rather than reset it, silently
  making the supervisor think old steps are still done. A fresh thread_id
  has no accumulated state to fight with. Real incremental multi-turn
  refinement (editing just the affected steps) is Week 21's job — this is
  honest, correct infrastructure for it to build on, not the sophisticated
  version yet.
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
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from travel_agent.agents.graph import build_planning_graph, build_sqlite_checkpointer
from travel_agent.api.schemas import (
    PlanRequest,
    PlanResponse,
    RefineRequest,
    ResumeRequest,
    SessionStateResponse,
)
from travel_agent.api.sessions import SessionStore
from travel_agent.config import settings
from travel_agent.models.core import Itinerary
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
    session_store: SessionStore | None = None,
    narrator: ItineraryNarrator | None = None,
    parser: PreferenceParser | None = None,
) -> FastAPI:
    graph = graph or build_planning_graph(checkpointer=build_sqlite_checkpointer())
    session_store = session_store or SessionStore()
    narrator = narrator or ItineraryNarrator()
    parser = parser or PreferenceParser()

    limiter = Limiter(key_func=get_remote_address)
    app = FastAPI(title="Autonomous AI Travel Planning Agent", version="0.1.0")
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

    def _config(session_id: str) -> dict:
        return {"configurable": {"thread_id": session_id}}

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

    @app.post(
        "/plan",
        response_model=PlanResponse,
        status_code=202,
        dependencies=[Depends(verify_api_key)],
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
    )
    async def get_plan(session_id: str) -> SessionStateResponse:
        return _state_response(session_id)

    @app.post(
        "/plan/{session_id}/resume",
        response_model=PlanResponse,
        dependencies=[Depends(verify_api_key)],
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
    )
    @limiter.limit(PLAN_RATE_LIMIT)
    async def refine(request: Request, body: RefineRequest) -> PlanResponse:
        if session_store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="session not found")
        existing_prefs = graph.get_state(_config(body.session_id)).values.get("preferences") or {}

        parsed = await asyncio.to_thread(parser.parse, body.raw_text)
        updates = {
            k: v
            for k, v in parsed.model_dump(mode="json").items()
            if k != "raw_text" and v not in (None, [], {}, "")
        }
        merged_preferences = {**existing_prefs, **updates, "raw_text": body.raw_text}

        new_session_id = str(uuid.uuid4())
        session_store.create(new_session_id, body.raw_text, parent_session_id=body.session_id)
        asyncio.create_task(
            _drive_graph(
                new_session_id,
                {
                    "raw_text": body.raw_text,
                    "preferences": merged_preferences,
                    "errors": [],
                    "completed_steps": ["parse_preferences"],
                },
            )
        )
        return PlanResponse(session_id=new_session_id, status="running")

    @app.get("/export/{session_id}/pdf", dependencies=[Depends(verify_api_key)])
    async def export_pdf(session_id: str) -> FileResponse:
        pdf_path = (graph.get_state(_config(session_id)).values or {}).get("pdf_path")
        if not pdf_path or not Path(pdf_path).exists():
            raise HTTPException(status_code=404, detail="PDF not available for this session")
        return FileResponse(pdf_path, media_type="application/pdf", filename=Path(pdf_path).name)

    @app.get("/export/{session_id}/map", dependencies=[Depends(verify_api_key)])
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
