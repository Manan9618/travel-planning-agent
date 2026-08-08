"""Pydantic request/response models for the FastAPI layer — Week 15 deliverable.

Kept separate from `models/core.py`: these describe the HTTP/WebSocket
*wire format*, not the shared domain layer every tool operates on.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    raw_text: str = Field(min_length=1, description="Natural language travel request")


class PlanResponse(BaseModel):
    session_id: str
    status: str


class ResumeRequest(BaseModel):
    approved: bool


class RefineRequest(BaseModel):
    session_id: str
    raw_text: str = Field(min_length=1, description="Natural language refinement request")


class SessionStateResponse(BaseModel):
    session_id: str
    status: str
    completed_steps: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    preferences: dict[str, Any] | None = None
    itinerary: dict[str, Any] | None = None
    conflict_log: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    budget_evaluation: dict[str, Any] | None = None
    pdf_path: str | None = None
    map_html_available: bool = False
