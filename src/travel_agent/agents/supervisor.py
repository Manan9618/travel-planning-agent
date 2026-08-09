"""SupervisorAgent — Week 4 deliverable.

Picks the next step to run. Originally, when several independent tools were all
ready at once (flights/hotels/attractions/restaurants/weather), an LLM call broke
the tie by choosing an order. Week 20 replaced that: `determine_valid_steps` only
ever returns more than one step for that exact search phase, and those tools don't
depend on each other or on one another's results, so order never affected
correctness — the LLM call was pure cost and latency for a decision that didn't
matter. `graph.py`'s `make_supervisor_node` now fans all of them out to run in the
same LangGraph superstep instead of asking an LLM to sequence them, so this class
never sees more than one valid step and makes no LLM calls at all.
"""

from __future__ import annotations

from travel_agent.agents.state import PlanningState, PlanningStep, determine_valid_steps


class SupervisorAgent:
    def decide_next(self, state: PlanningState) -> PlanningStep:
        return determine_valid_steps(state)[0]
