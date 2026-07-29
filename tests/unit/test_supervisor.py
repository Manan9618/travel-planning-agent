from unittest.mock import MagicMock

import pytest

from travel_agent.agents.state import PlanningStep
from travel_agent.agents.supervisor import SupervisorAgent, _StepChoice


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


def test_single_valid_step_skips_llm_entirely(monkeypatch):
    supervisor = SupervisorAgent()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called when only one step is valid")

    monkeypatch.setattr(supervisor, "_invoke", fail_if_called)
    result = supervisor.decide_next({})
    assert result == PlanningStep.PARSE_PREFERENCES


def test_llm_choice_is_used_when_valid(monkeypatch):
    supervisor = SupervisorAgent()
    monkeypatch.setattr(
        supervisor,
        "_invoke",
        lambda state, valid: _StepChoice(next_step="check_weather", reasoning="trip is soon"),
    )
    result = supervisor.decide_next(_state_with_multiple_valid_steps())
    assert result == PlanningStep.CHECK_WEATHER


def test_invalid_llm_choice_falls_back_to_first_valid(monkeypatch):
    supervisor = SupervisorAgent()
    monkeypatch.setattr(
        supervisor,
        "_invoke",
        lambda state, valid: _StepChoice(next_step="not_a_real_step", reasoning="oops"),
    )
    state = _state_with_multiple_valid_steps()
    from travel_agent.agents.state import determine_valid_steps

    expected_first = determine_valid_steps(state)[0]
    result = supervisor.decide_next(state)
    assert result == expected_first


def test_llm_exception_falls_back_to_first_valid(monkeypatch):
    supervisor = SupervisorAgent()

    def raise_error(state, valid):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(supervisor, "_invoke", raise_error)
    state = _state_with_multiple_valid_steps()
    from travel_agent.agents.state import determine_valid_steps

    expected_first = determine_valid_steps(state)[0]
    result = supervisor.decide_next(state)
    assert result == expected_first


def test_invoke_retries_then_succeeds(monkeypatch):
    supervisor = SupervisorAgent()
    good_result = _StepChoice(next_step="search_flights", reasoning="budget first")
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [RuntimeError("timeout"), good_result]
    monkeypatch.setattr(supervisor, "_llm", mock_llm)

    result = supervisor._invoke(_state_with_multiple_valid_steps(), [PlanningStep.SEARCH_FLIGHTS])
    assert result == good_result
    assert mock_llm.invoke.call_count == 2


def test_invoke_raises_value_error_on_unstructured_response(monkeypatch):
    supervisor = SupervisorAgent()
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = {"not": "structured"}
    monkeypatch.setattr(supervisor, "_llm", mock_llm)

    with pytest.raises(ValueError):
        supervisor._invoke(_state_with_multiple_valid_steps(), [PlanningStep.SEARCH_FLIGHTS])


def test_summarize_includes_key_trip_details():
    summary = SupervisorAgent._summarize(
        _state_with_multiple_valid_steps(),
        [PlanningStep.SEARCH_FLIGHTS, PlanningStep.SEARCH_HOTELS],
    )
    assert "Paris" in summary
    assert "Boston" in summary
    assert "2000" in summary
    assert "art" in summary
