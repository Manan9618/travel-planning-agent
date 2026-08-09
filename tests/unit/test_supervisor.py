from travel_agent.agents.state import PlanningStep, determine_valid_steps
from travel_agent.agents.supervisor import SupervisorAgent


def _state_with_multiple_valid_steps():
    return {
        "preferences": {
            "origin": "Boston",
            "destination": "Paris",
            "start_date": "2026-09-01",
            "budget_total": 2000,
            "interests": ["art"],
        },
        "completed_steps": ["parse_preferences"],
    }


def test_single_valid_step_is_returned_directly():
    supervisor = SupervisorAgent()
    result = supervisor.decide_next({})
    assert result == PlanningStep.PARSE_PREFERENCES


def test_multiple_valid_steps_returns_first_without_any_llm_call():
    """Week 20: SupervisorAgent makes no LLM calls at all - the graph's own
    `make_supervisor_node` fans multiple valid steps out to run in parallel
    instead of ever asking this class to break the tie. Calling
    `decide_next` directly (as e.g. a fake/stub supervisor might) still
    returns a sane default: the first structurally-valid step."""
    supervisor = SupervisorAgent()
    state = _state_with_multiple_valid_steps()
    expected_first = determine_valid_steps(state)[0]
    result = supervisor.decide_next(state)
    assert result == expected_first
