"""ItineraryNarrator — Week 15 deliverable: a genuine token-by-token LLM
narration of a built itinerary, streamed over the FastAPI WebSocket endpoint.

Every other planning step is either a deterministic computation or an LLM
call using structured output (which doesn't produce meaningful partial text
to stream) — this is the one place a plain, free-text streaming completion
actually makes sense, so it's the piece that gives the WebSocket endpoint
genuine "token-by-token" streaming rather than just step-progress events.
Reuses Week 12's `render_itinerary_summary` so the narrator sees the same
compact day-by-day text the LLM judge already relies on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_openai import ChatOpenAI

from travel_agent.config import settings
from travel_agent.models.core import Itinerary
from travel_agent.observability.metrics import record_llm_usage
from travel_agent.tools.itinerary_judge import render_itinerary_summary

_SYSTEM_PROMPT = """You are a friendly, enthusiastic travel agent. Write a warm 3-5 sentence \
narrative summary of the trip described, as if presenting it back to the traveler. Mention \
the destination, trip length, and one or two specific highlights. Do not invent details not \
present in the itinerary. No markdown, no headings — just prose."""


class ItineraryNarrator:
    def __init__(self, model: str | None = None, temperature: float = 0.4) -> None:
        self._model = model or settings.openai_model
        self._llm = ChatOpenAI(
            model=self._model,
            temperature=temperature,
            api_key=settings.openai_api_key or None,
            streaming=True,
            stream_usage=True,
        )

    async def narrate(self, itinerary: Itinerary) -> AsyncIterator[str]:
        summary = render_itinerary_summary(itinerary.preferences, itinerary)
        messages = [("system", _SYSTEM_PROMPT), ("human", summary)]
        # AIMessageChunks support `+` accumulation; with stream_usage=True the
        # running total's usage_metadata carries real token counts once every
        # chunk has been folded in (Week 19 cost tracking) - a single field
        # on the LAST raw chunk wouldn't work since content and usage arrive
        # on different chunks during a real stream.
        accumulated = None
        async for chunk in self._llm.astream(messages):
            if chunk.content:
                yield chunk.content
            accumulated = chunk if accumulated is None else accumulated + chunk
        if accumulated is not None:
            record_llm_usage(self._model, accumulated.usage_metadata)
