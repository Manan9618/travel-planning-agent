"""Pydantic request/response models for the FastAPI layer — Week 15 deliverable.

Kept separate from `models/core.py`: these describe the HTTP/WebSocket
*wire format*, not the shared domain layer every tool operates on.

Field-level `examples` (Week 23) populate the "Example Value" shown for each
schema on the auto-generated `/docs` page (Swagger UI) and `/redoc` — no
separate example-maintenance file, since Pydantic renders these directly
into the OpenAPI schema FastAPI already generates from these classes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    """Body for `POST /plan` — a brand-new trip request."""

    raw_text: str = Field(
        min_length=1,
        description="Natural language travel request. Must state a destination "
        "(dates, origin, and budget are optional and inferred where possible).",
        examples=["5 days in Paris this September under $2000, I love art and museums"],
    )


class PlanResponse(BaseModel):
    """Returned immediately (202 Accepted) by `POST /plan`, `/refine`, and
    `/resume` — the actual planning run continues in the background; poll
    `GET /plan/{session_id}` or connect to `WS /ws/{session_id}` for progress."""

    session_id: str = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    status: str = Field(examples=["running"])


class ResumeRequest(BaseModel):
    """Body for `POST /plan/{session_id}/resume` — the traveler's decision
    on an unresolved conflict raised during Week 6's human-in-the-loop pause
    (e.g. a budget overrun that couldn't be automatically resolved)."""

    approved: bool = Field(
        description="Whether the traveler approves proceeding despite the "
        "unresolved conflict shown in the awaiting_review WebSocket event.",
        examples=[True],
    )


class RefineRequest(BaseModel):
    """Body for `POST /refine` — a follow-up request against an existing
    session. As of Week 21, only the search steps whose inputs actually
    changed re-run; unaffected results are carried over from the parent
    session (see `agents/refinement.py`)."""

    session_id: str = Field(
        description="The session_id of a completed or awaiting-review parent session.",
        examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"],
    )
    raw_text: str = Field(
        min_length=1,
        description="Natural language refinement request. Need not restate the "
        "whole trip — only what's changing.",
        examples=["actually make it more relaxing, and add a museum visit"],
    )


class SessionStateResponse(BaseModel):
    """Returned by `GET /plan/{session_id}` — the full current state of a
    planning session, whether still running, completed, awaiting human
    review, or failed."""

    session_id: str = Field(examples=["3fa85f64-5717-4562-b3fc-2c963f66afa6"])
    status: str = Field(
        description="One of: running, completed, awaiting_review, failed.",
        examples=["completed"],
    )
    completed_steps: list[str] = Field(
        default_factory=list,
        description="Planning steps finished so far, e.g. search_flights, "
        "build_itinerary — see agents/state.py's PlanningStep for the full list.",
        examples=[["parse_preferences", "search_flights", "search_hotels"]],
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Non-fatal errors from individual steps (e.g. a hotel API "
        "timeout) — the run continues past these, falling back to mock data "
        "where applicable rather than halting.",
    )
    preferences: dict[str, Any] | None = Field(
        default=None, description="Parsed TravelPreferences, once parse_preferences completes."
    )
    itinerary: dict[str, Any] | None = Field(
        default=None, description="The full day-by-day Itinerary, once build_itinerary completes."
    )
    conflict_log: list[dict[str, Any]] = Field(
        default_factory=list, description="Every conflict found and how (if) it was resolved."
    )
    unresolved_conflicts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Conflicts that couldn't be auto-resolved — present only "
        "when status is awaiting_review.",
    )
    budget_evaluation: dict[str, Any] | None = Field(
        default=None, description="Budget adherence and per-category cost breakdown."
    )
    pdf_path: str | None = Field(
        default=None,
        description="Server-side path to the generated PDF, if generate_pdf completed.",
    )
    map_html_available: bool = Field(
        default=False,
        description="Whether an interactive map is ready at GET /export/{session_id}/map.",
    )
