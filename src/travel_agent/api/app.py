"""FastAPI backend — Week 15 deliverable.

Exposes the LangGraph planning pipeline (Weeks 1-14) over HTTP + WebSocket:

- `POST /auth/register` and `POST /auth/login` create/authenticate a real
  account (bcrypt-hashed password, `api/users.py`) and return a signed JWT
  bearer token (`api/auth.py`). Every session-scoped endpoint below requires
  it (`Authorization: Bearer <token>`, or `?token=` on the WebSocket, which
  can't set custom headers) and enforces that a session belongs to the
  requesting user — a session created before accounts existed, or by a
  different user, 404s rather than leaking that it exists. Separate from
  `verify_api_key` (an older, optional, deployment-wide shared secret,
  still supported and independent of per-user auth — both can be active
  at once). `POST /auth/forgot-password` + `/reset-password` round out
  account management: a short-lived (15 min default), purpose-scoped JWT
  distinct from a bearer token (`create_reset_token`/`decode_reset_token`)
  emailed via `EmailSender` — which logs the reset link instead of sending
  when SMTP isn't configured, same graceful-degradation pattern as every
  other optional integration in this project. `GET /auth/google/login` +
  `/callback` add "Continue with Google" — same JWT bearer token out the
  other end as register/login, just reached via Google's consent screen
  instead of a password (`tools/google_oauth.py`'s `GoogleOAuthClient`;
  matched to an existing account by Google's own account id first, then by
  email, so a password account signing in with Google for the first time
  gets linked rather than duplicated).
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
  artifacts; `/calendar` generates a .ics file on the fly (one VEVENT per
  scheduled item) rather than persisting one, since it's cheap to rebuild
  and every other export already reads from the same graph state.
- `POST /plan/{session_id}/share` mints an opaque, unguessable share token
  (`sessions.share_token`); `GET /shared/{token}` and its own `/pdf`/`/map`
  serve a read-only view keyed by that token instead of session_id+owner —
  the one deliberate hole in the "every session-scoped endpoint requires a
  bearer token" rule above, since a public link has to work for someone
  with no account at all.
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
import secrets
import time
import uuid
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
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
from travel_agent.api.auth import (
    create_access_token,
    create_oauth_state_token,
    create_reset_token,
    decode_access_token,
    decode_reset_token,
    extract_bearer_token,
    hash_password,
    is_valid_email,
    verify_oauth_state_token,
    verify_password,
)
from travel_agent.api.schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    PlanRequest,
    PlanResponse,
    RefineRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResumeRequest,
    SessionListResponse,
    SessionStateResponse,
    SessionSummary,
    SharedTripResponse,
    ShareResponse,
    UserResponse,
)
from travel_agent.api.sessions import PostgresSessionStore, SessionStore, build_session_store
from travel_agent.api.users import PostgresUserStore, UserRecord, UserStore, build_user_store
from travel_agent.config import settings
from travel_agent.models.core import Itinerary
from travel_agent.observability.logging import (
    bind_request_context,
    clear_request_context,
    configure_logging,
)
from travel_agent.observability.metrics import PLANNING_DURATION
from travel_agent.observability.sentry import init_sentry
from travel_agent.tools.calendar_export import generate_ics
from travel_agent.tools.email_sender import EmailSender
from travel_agent.tools.google_oauth import GoogleOAuthClient
from travel_agent.tools.itinerary_narrator import ItineraryNarrator
from travel_agent.tools.preference_parser import PreferenceParser

logger = logging.getLogger(__name__)

WS_POLL_INTERVAL_SECONDS = 0.2
TERMINAL_EVENT_TYPES = {"done", "error", "awaiting_review"}
PLAN_RATE_LIMIT = "10/minute"
# Tighter than PLAN_RATE_LIMIT: login/register are the endpoints a
# credential-stuffing or fake-account-spam attempt would actually hit.
AUTH_RATE_LIMIT = "5/minute"


def verify_api_key(request: Request) -> None:
    if not settings.api_key:
        return  # no key configured -> auth disabled (local/dev default)
    if request.headers.get("X-API-Key") != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def create_app(
    graph: CompiledStateGraph | None = None,
    session_store: SessionStore | PostgresSessionStore | None = None,
    user_store: UserStore | PostgresUserStore | None = None,
    narrator: ItineraryNarrator | None = None,
    parser: PreferenceParser | None = None,
    email_sender: EmailSender | None = None,
    google_oauth: GoogleOAuthClient | None = None,
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
    user_store = user_store or build_user_store(settings.database_url)
    narrator = narrator or ItineraryNarrator()
    parser = parser or PreferenceParser()
    email_sender = email_sender or EmailSender()
    google_oauth = google_oauth or GoogleOAuthClient(
        client_id=settings.google_client_id, client_secret=settings.google_client_secret
    )

    def get_current_user(authorization: str | None = Header(default=None)) -> UserRecord:
        """FastAPI dependency: the authenticated user, from a real JWT
        bearer token — separate from `verify_api_key` above (see its own
        docstring). Any REST endpoint that reads/writes a specific user's
        sessions takes this as a parameter (not just in `dependencies=`) so
        its handler can use `current_user.user_id`. Defined up here, before
        the routes below, since several of them reference it as a default
        argument (`Depends(get_current_user)`), which Python evaluates once
        at each route function's *definition* time, not at request time."""
        token = extract_bearer_token(authorization)
        user_id = decode_access_token(token)
        user = user_store.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="user not found")
        return user

    def _get_owned_session(session_id: str, user_id: str) -> None:
        """404 (never 403) for a session that doesn't exist OR belongs to
        someone else — same reasoning REST APIs generally use for
        per-owner resources: a 403 would confirm the session_id is real,
        which is itself information a non-owner shouldn't get for free."""
        record = session_store.get(session_id)
        if record is None or record.user_id != user_id:
            raise HTTPException(status_code=404, detail="session not found")

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

    @app.post(
        "/auth/register",
        response_model=AuthResponse,
        status_code=201,
        tags=["auth"],
        summary="Create an account",
        description="Registers a new user (email + password, bcrypt-hashed — "
        "never stored or logged in plaintext) and returns a bearer token, the "
        "same as /auth/login would for that account immediately afterward. "
        "Deliberately NOT behind `verify_api_key`, unlike every session-scoped "
        "endpoint below — an API_KEY-protected deployment would otherwise lock "
        "out registration itself, since there'd be no way to get a JWT to send "
        "in the first place.",
    )
    @limiter.limit(AUTH_RATE_LIMIT)
    async def register(request: Request, body: RegisterRequest) -> AuthResponse:
        if not is_valid_email(body.email):
            raise HTTPException(status_code=422, detail="invalid email address")
        if user_store.get_by_email(body.email) is not None:
            raise HTTPException(status_code=409, detail="email already registered")
        user_id = str(uuid.uuid4())
        user_store.create(user_id, body.email, hash_password(body.password))
        return AuthResponse(
            access_token=create_access_token(user_id), user_id=user_id, email=body.email.lower()
        )

    @app.post(
        "/auth/login",
        response_model=AuthResponse,
        tags=["auth"],
        summary="Log in",
        description="Exchanges an existing account's email + password for a "
        "bearer token — send it back as `Authorization: Bearer <token>` on "
        "every session-scoped request. Also not behind `verify_api_key`, for "
        "the same reason /auth/register isn't.",
    )
    @limiter.limit(AUTH_RATE_LIMIT)
    async def login(request: Request, body: LoginRequest) -> AuthResponse:
        user = user_store.get_by_email(body.email)
        # Same error for "no such user" and "wrong password" - confirming an
        # email is registered at all is its own small information leak.
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=401, detail="invalid email or password")
        return AuthResponse(
            access_token=create_access_token(user.user_id), user_id=user.user_id, email=user.email
        )

    @app.post(
        "/auth/forgot-password",
        response_model=MessageResponse,
        tags=["auth"],
        summary="Request a password reset",
        description="Always returns the same message whether or not the "
        "email is registered, to avoid leaking which emails have accounts "
        "— same principle as /auth/login's identical error for 'no such "
        "user' and 'wrong password'. If the email IS registered, a reset "
        "link (valid for a short time) is emailed to it. Not behind "
        "`verify_api_key`, for the same reason /auth/register isn't.",
    )
    @limiter.limit(AUTH_RATE_LIMIT)
    async def forgot_password(request: Request, body: ForgotPasswordRequest) -> MessageResponse:
        user = user_store.get_by_email(body.email)
        if user is not None:
            reset_token = create_reset_token(user.user_id)
            reset_url = f"{settings.frontend_base_url}/?reset_token={reset_token}"
            email_sender.send(
                user.email,
                "Reset your Waypoint password",
                "Someone requested a password reset for this account. If this "
                f"was you, reset your password here (valid for "
                f"{settings.password_reset_expire_minutes} minutes):\n\n{reset_url}\n\n"
                "If this wasn't you, you can safely ignore this email.",
            )
        return MessageResponse(message="If that email is registered, a reset link has been sent.")

    @app.post(
        "/auth/reset-password",
        response_model=MessageResponse,
        tags=["auth"],
        summary="Reset a password using a reset link's token",
        description="Exchanges a valid, unexpired reset token (from the "
        "emailed link) for a new password. `token` here is a short-lived "
        "reset token, not a bearer access token — see /auth/forgot-password. "
        "Not behind `verify_api_key`, for the same reason /auth/register "
        "isn't.",
    )
    @limiter.limit(AUTH_RATE_LIMIT)
    async def reset_password(request: Request, body: ResetPasswordRequest) -> MessageResponse:
        user_id = decode_reset_token(body.token)
        user = user_store.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=400, detail="invalid or expired reset link")
        user_store.update_password(user_id, hash_password(body.new_password))
        return MessageResponse(
            message="Password updated — you can now sign in with your new password."
        )

    @app.get(
        "/auth/me",
        response_model=UserResponse,
        dependencies=[Depends(verify_api_key)],
        tags=["auth"],
        summary="Get the current user",
        description="Returns the account for the bearer token sent — lets the "
        "frontend validate a stored token and recover the user's email on "
        "app load without re-decoding the JWT client-side.",
    )
    async def me(current_user: UserRecord = Depends(get_current_user)) -> UserResponse:
        return UserResponse(user_id=current_user.user_id, email=current_user.email)

    def _google_callback_url() -> str:
        return f"{settings.backend_base_url}/auth/google/callback"

    @app.get(
        "/auth/google/login",
        tags=["auth"],
        summary="Start Google sign-in",
        description="Redirects to Google's own consent screen. Not behind "
        "`verify_api_key`, for the same reason /auth/register isn't — there's "
        "no bearer token to send yet. If GOOGLE_CLIENT_ID/SECRET aren't "
        "configured, redirects straight back to the frontend with "
        "`?oauth_error=not_configured` instead of erroring, the same "
        "optional-credential degradation every other integration in this "
        "project uses.",
    )
    @limiter.limit(AUTH_RATE_LIMIT)
    async def google_login(request: Request) -> RedirectResponse:
        if not google_oauth.configured:
            return RedirectResponse(f"{settings.frontend_base_url}/?oauth_error=not_configured")
        state = create_oauth_state_token()
        return RedirectResponse(google_oauth.authorize_url(_google_callback_url(), state))

    @app.get(
        "/auth/google/callback",
        tags=["auth"],
        summary="Google sign-in callback",
        description="Where Google redirects back to after the consent "
        "screen. Exchanges the one-time code for an access token, looks up "
        "or creates the account (matched by Google's own account id first, "
        "then by email — so an existing password account signing in with "
        "Google the first time gets linked rather than duplicated), and "
        "redirects to the frontend with `?oauth_token=<bearer token>` — "
        "or `?oauth_error=<reason>` if anything along the way failed. Not "
        "behind `verify_api_key`, for the same reason /auth/google/login "
        "isn't.",
    )
    async def google_callback(
        code: str | None = None, state: str | None = None, error: str | None = None
    ) -> RedirectResponse:
        if error:
            return RedirectResponse(f"{settings.frontend_base_url}/?oauth_error=denied")
        if not code or not state:
            return RedirectResponse(f"{settings.frontend_base_url}/?oauth_error=invalid_request")
        try:
            verify_oauth_state_token(state)
        except HTTPException:
            return RedirectResponse(f"{settings.frontend_base_url}/?oauth_error=invalid_state")

        try:
            access_token = google_oauth.exchange_code(code, _google_callback_url())
            userinfo = google_oauth.fetch_userinfo(access_token)
            google_id = userinfo["sub"]
            email = userinfo["email"]
        except Exception as exc:
            logger.warning("google oauth exchange failed: %s", exc)
            return RedirectResponse(f"{settings.frontend_base_url}/?oauth_error=exchange_failed")

        user = user_store.get_by_google_id(google_id)
        if user is None:
            user = user_store.get_by_email(email)
            if user is not None:
                user_store.link_google_id(user.user_id, google_id)
            else:
                user_id = str(uuid.uuid4())
                # A Google-only account still needs *some* password_hash
                # (the column stays NOT NULL — see users.py's module
                # docstring) — a random value nobody will ever type in
                # simply never verifies true, which is exactly the
                # behavior a "no password set" account should have.
                user_store.create(
                    user_id, email, hash_password(secrets.token_urlsafe(32)), google_id=google_id
                )
                user = user_store.get_by_id(user_id)

        token = create_access_token(user.user_id)
        return RedirectResponse(f"{settings.frontend_base_url}/?oauth_token={token}")

    @app.get(
        "/sessions",
        response_model=SessionListResponse,
        dependencies=[Depends(verify_api_key)],
        tags=["sessions"],
        summary="List my trips",
        description="Returns the current user's trips, most recent first — "
        "one entry per top-level /plan request (not one per /refine "
        "follow-up), for a trip-history dashboard.",
    )
    async def list_sessions(
        current_user: UserRecord = Depends(get_current_user),
    ) -> SessionListResponse:
        records = session_store.list_by_user(current_user.user_id)
        return SessionListResponse(
            sessions=[
                SessionSummary(
                    session_id=r.session_id,
                    raw_text=r.raw_text,
                    status=r.status,
                    created_at=r.created_at,
                )
                for r in records
            ]
        )

    @app.delete(
        "/sessions/{session_id}",
        status_code=204,
        dependencies=[Depends(verify_api_key)],
        tags=["sessions"],
        summary="Delete a trip",
        description="Permanently deletes a session's metadata and event "
        "log. Does not cascade to /refine follow-ups created from it — they "
        "simply become unreachable from the dashboard, the same outcome "
        "sessions created before user accounts existed already have.",
    )
    async def delete_session(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> Response:
        _get_owned_session(session_id, current_user.user_id)
        session_store.delete(session_id)
        return Response(status_code=204)

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
    async def plan(
        request: Request, body: PlanRequest, current_user: UserRecord = Depends(get_current_user)
    ) -> PlanResponse:
        session_id = str(uuid.uuid4())
        session_store.create(session_id, body.raw_text, user_id=current_user.user_id)
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
    async def get_plan(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> SessionStateResponse:
        _get_owned_session(session_id, current_user.user_id)
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
    async def resume_plan(
        session_id: str, body: ResumeRequest, current_user: UserRecord = Depends(get_current_user)
    ) -> PlanResponse:
        _get_owned_session(session_id, current_user.user_id)
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
    async def refine(
        request: Request,
        body: RefineRequest,
        current_user: UserRecord = Depends(get_current_user),
    ) -> PlanResponse:
        _get_owned_session(body.session_id, current_user.user_id)
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
        session_store.create(
            new_session_id,
            body.raw_text,
            parent_session_id=body.session_id,
            user_id=current_user.user_id,
        )
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
    async def export_pdf(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> FileResponse:
        _get_owned_session(session_id, current_user.user_id)
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
    async def export_map(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> HTMLResponse:
        _get_owned_session(session_id, current_user.user_id)
        map_html = (graph.get_state(_config(session_id)).values or {}).get("map_html")
        if not map_html:
            raise HTTPException(status_code=404, detail="map not available for this session")
        return HTMLResponse(map_html)

    @app.get(
        "/export/{session_id}/calendar",
        dependencies=[Depends(verify_api_key)],
        tags=["export"],
        summary="Download the itinerary as a calendar file",
        description="Returns a .ics file (one event per scheduled item) once "
        "build_itinerary has completed, importable into Google Calendar, "
        "Apple Calendar, Outlook, or any other RFC 5545 client.",
    )
    async def export_calendar(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> Response:
        _get_owned_session(session_id, current_user.user_id)
        itinerary_data = (graph.get_state(_config(session_id)).values or {}).get("itinerary")
        if not itinerary_data:
            raise HTTPException(status_code=404, detail="itinerary not available for this session")
        ics_text = generate_ics(Itinerary(**itinerary_data))
        return Response(
            content=ics_text,
            media_type="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="itinerary-{session_id}.ics"'},
        )

    @app.post(
        "/plan/{session_id}/share",
        response_model=ShareResponse,
        dependencies=[Depends(verify_api_key)],
        tags=["sharing"],
        summary="Create a public share link for a trip",
        description="Generates (or returns the existing) opaque share token "
        "for this session and returns a public, unauthenticated URL anyone "
        "with the link can use to view a read-only copy via GET "
        "/shared/{token} — no session internals (status, errors, conflict "
        "history) are exposed. Requires build_itinerary to have already run.",
    )
    async def create_share_link(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> ShareResponse:
        _get_owned_session(session_id, current_user.user_id)
        itinerary_data = (graph.get_state(_config(session_id)).values or {}).get("itinerary")
        if not itinerary_data:
            raise HTTPException(status_code=400, detail="trip isn't ready to share yet")
        record = session_store.get(session_id)
        token = record.share_token or secrets.token_urlsafe(24)
        if not record.share_token:
            session_store.set_share_token(session_id, token)
        return ShareResponse(share_url=f"{settings.frontend_base_url}/?shared={token}")

    @app.delete(
        "/plan/{session_id}/share",
        status_code=204,
        dependencies=[Depends(verify_api_key)],
        tags=["sharing"],
        summary="Revoke a trip's share link",
        description="The existing link stops working immediately — "
        "GET /shared/{token} 404s from this point on. Safe to call even if "
        "the trip was never shared.",
    )
    async def revoke_share_link(
        session_id: str, current_user: UserRecord = Depends(get_current_user)
    ) -> Response:
        _get_owned_session(session_id, current_user.user_id)
        session_store.clear_share_token(session_id)
        return Response(status_code=204)

    @app.get(
        "/shared/{token}",
        response_model=SharedTripResponse,
        tags=["sharing"],
        summary="View a publicly shared trip",
        description="No authentication required — deliberately public, "
        "reachable by anyone with the link. Not behind verify_api_key "
        "either: a stranger opening a shared link has neither a bearer "
        "token nor the deployment's API key, the same bootstrap reasoning "
        "that exempts /auth/register and /auth/login.",
    )
    async def get_shared_trip(token: str) -> SharedTripResponse:
        record = session_store.get_by_share_token(token)
        if record is None:
            raise HTTPException(status_code=404, detail="shared trip not found")
        values = graph.get_state(_config(record.session_id)).values or {}
        return SharedTripResponse(
            itinerary=values.get("itinerary"),
            budget_evaluation=values.get("budget_evaluation"),
            pdf_available=bool(values.get("pdf_path")),
            map_available=bool(values.get("map_html")),
        )

    @app.get(
        "/shared/{token}/pdf",
        tags=["sharing"],
        summary="Download a publicly shared trip's PDF",
        response_class=FileResponse,
    )
    async def get_shared_pdf(token: str) -> FileResponse:
        record = session_store.get_by_share_token(token)
        if record is None:
            raise HTTPException(status_code=404, detail="shared trip not found")
        pdf_path = (graph.get_state(_config(record.session_id)).values or {}).get("pdf_path")
        if not pdf_path or not Path(pdf_path).exists():
            raise HTTPException(status_code=404, detail="PDF not available for this trip")
        return FileResponse(pdf_path, media_type="application/pdf", filename=Path(pdf_path).name)

    @app.get(
        "/shared/{token}/map",
        tags=["sharing"],
        summary="View a publicly shared trip's interactive map",
        response_class=HTMLResponse,
    )
    async def get_shared_map(token: str) -> HTMLResponse:
        record = session_store.get_by_share_token(token)
        if record is None:
            raise HTTPException(status_code=404, detail="shared trip not found")
        map_html = (graph.get_state(_config(record.session_id)).values or {}).get("map_html")
        if not map_html:
            raise HTTPException(status_code=404, detail="map not available for this trip")
        return HTMLResponse(map_html)

    @app.websocket("/ws/{session_id}")
    async def ws_stream(
        websocket: WebSocket, session_id: str, token: str | None = Query(default=None)
    ) -> None:
        await websocket.accept()
        # Browsers' native WebSocket API can't set an Authorization header,
        # so the bearer token travels as ?token=... instead - decode_access_token
        # raises HTTPException on failure, which means nothing to a raw
        # WebSocket, so it's translated into the same graceful
        # error-then-close pattern the "session not found" case already uses.
        try:
            user_id = decode_access_token(
                extract_bearer_token(f"Bearer {token}" if token else None)
            )
        except HTTPException:
            await websocket.send_json({"type": "error", "message": "missing or invalid token"})
            await websocket.close()
            return
        record = session_store.get(session_id)
        if record is None or record.user_id != user_id:
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
