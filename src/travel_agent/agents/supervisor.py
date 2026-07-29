"""SupervisorAgent — Week 4 deliverable.

Decides which tool to run next. When only one step is structurally valid (see
`determine_valid_steps`), it's chosen directly with no LLM call. When several
independent tools are all ready to run (flights/hotels/attractions/restaurants/
weather), an LLM picks the order given a summary of the trip so far — e.g. it might
front-load weather when the trip is soon, or budget-sensitive tools first when
budget is tight. The choice is always validated against the allowed set before use,
falling back to the first valid option if the model returns anything else.
"""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from travel_agent.agents.state import PlanningState, PlanningStep, determine_valid_steps
from travel_agent.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the supervisor of a travel-planning agent. Given the \
current planning state and a list of allowed next steps, pick exactly one step to \
run next. Prefer an order that best serves the traveler (e.g. checking weather \
before recommending attractions if the trip is imminent, or searching flights \
first when budget is tight and flights usually dominate cost). You MUST choose \
one of the allowed steps verbatim."""


class _StepChoice(BaseModel):
    next_step: str = Field(description="one of the allowed step names, verbatim")
    reasoning: str = Field(description="one sentence explaining the choice")


class SupervisorAgent:
    def __init__(self, model: str | None = None) -> None:
        self._llm = ChatOpenAI(
            model=model or settings.openai_model,
            temperature=0,
            api_key=settings.openai_api_key or None,
        ).with_structured_output(_StepChoice)

    def decide_next(self, state: PlanningState) -> PlanningStep:
        valid = determine_valid_steps(state)
        if len(valid) == 1:
            return valid[0]

        try:
            choice = self._invoke(state, valid)
        except Exception as exc:
            logger.warning("Supervisor LLM call failed (%s); defaulting to %s", exc, valid[0])
            return valid[0]

        for step in valid:
            if step.value == choice.next_step:
                return step
        logger.warning(
            "Supervisor returned invalid step %r, not in %s; defaulting to %s",
            choice.next_step,
            [s.value for s in valid],
            valid[0],
        )
        return valid[0]

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=3),
        reraise=True,
    )
    def _invoke(self, state: PlanningState, valid: list[PlanningStep]) -> _StepChoice:
        summary = self._summarize(state, valid)
        messages = [("system", _SYSTEM_PROMPT), ("human", summary)]
        result = self._llm.invoke(messages)
        if not isinstance(result, _StepChoice):
            raise ValueError("LLM did not return structured output")
        return result

    @staticmethod
    def _summarize(state: PlanningState, valid: list[PlanningStep]) -> str:
        prefs = state.get("preferences") or {}
        lines = [
            f"Destination: {prefs.get('destination')}",
            f"Origin: {prefs.get('origin')}",
            f"Dates: {prefs.get('start_date')} to {prefs.get('end_date')}",
            f"Budget: {prefs.get('budget_total')} {prefs.get('budget_currency', 'USD')}",
            f"Interests: {prefs.get('interests')}",
            f"Already completed: {state.get('completed_steps', [])}",
            f"Allowed next steps: {[s.value for s in valid]}",
        ]
        return "\n".join(lines)
