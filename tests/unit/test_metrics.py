"""Week 19 Prometheus metrics tests.

Metric objects in `observability/metrics.py` are module-level singletons
(the standard prometheus_client idiom - one registry for the whole
process), so these tests assert on the DELTA a call produces (read the
current value, act, read again) rather than an absolute value, since other
tests in the same process may have already incremented the same series.
"""

from __future__ import annotations

from travel_agent.observability.metrics import (
    BUDGET_ADHERENCE,
    LLM_COST_USD,
    LLM_TOKENS,
    PLANNING_STEP_CALLS,
    PLANNING_STEP_DURATION,
    instrument_node,
    record_llm_usage,
)


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def _histogram_stat(histogram, stat: str, **labels) -> float:
    """Reads `<metric>_count` or `<metric>_sum` via the public `.collect()`
    API rather than a private attribute - needed for label-less histograms
    like BUDGET_ADHERENCE, where per-label private attributes don't apply
    the same way a plain Counter's `.labels(...)._value` does. Returns 0.0
    for a label combination never observed yet (prometheus_client creates
    a series lazily on first `.labels(...)` use, so it may genuinely not
    exist in `.collect()`'s output before a test's first observation)."""
    (metric,) = histogram.collect()
    for sample in metric.samples:
        if sample.name.endswith(f"_{stat}") and sample.labels == labels:
            return sample.value
    return 0.0


# --- instrument_node ---------------------------------------------------


def test_instrument_node_records_success_on_no_errors():
    node = lambda state: {"completed_steps": ["x"], "errors": []}  # noqa: E731
    wrapped = instrument_node("test_step_a", node)
    before = _counter_value(PLANNING_STEP_CALLS, step="test_step_a", status="success")

    wrapped({})

    after = _counter_value(PLANNING_STEP_CALLS, step="test_step_a", status="success")
    assert after == before + 1


def test_instrument_node_records_error_when_errors_present():
    node = lambda state: {"errors": ["boom"]}  # noqa: E731
    wrapped = instrument_node("test_step_b", node)
    before = _counter_value(PLANNING_STEP_CALLS, step="test_step_b", status="error")

    wrapped({})

    after = _counter_value(PLANNING_STEP_CALLS, step="test_step_b", status="error")
    assert after == before + 1


def test_instrument_node_records_duration():
    node = lambda state: {"errors": []}  # noqa: E731
    wrapped = instrument_node("test_step_c", node)
    before = _histogram_stat(PLANNING_STEP_DURATION, "count", step="test_step_c")

    wrapped({})

    after = _histogram_stat(PLANNING_STEP_DURATION, "count", step="test_step_c")
    assert after == before + 1


def test_instrument_node_returns_the_wrapped_nodes_result():
    node = lambda state: {"errors": [], "itinerary": {"days": []}}  # noqa: E731
    wrapped = instrument_node("test_step_d", node)
    assert wrapped({}) == {"errors": [], "itinerary": {"days": []}}


def test_instrument_node_records_budget_adherence_for_optimize_budget_step():
    node = lambda state: {  # noqa: E731
        "errors": [],
        "budget_evaluation": {"adherence_score": 0.85},
    }
    wrapped = instrument_node("optimize_budget", node)
    before = _histogram_stat(BUDGET_ADHERENCE, "sum")

    wrapped({})

    after = _histogram_stat(BUDGET_ADHERENCE, "sum")
    assert after == before + 0.85


def test_instrument_node_ignores_adherence_score_for_other_steps():
    node = lambda state: {  # noqa: E731
        "errors": [],
        "budget_evaluation": {"adherence_score": 0.5},
    }
    wrapped = instrument_node("check_weather", node)
    before = _histogram_stat(BUDGET_ADHERENCE, "count")

    wrapped({})

    assert _histogram_stat(BUDGET_ADHERENCE, "count") == before


def test_instrument_node_handles_missing_budget_evaluation_gracefully():
    node = lambda state: {"errors": []}  # noqa: E731
    wrapped = instrument_node("optimize_budget", node)
    # Should not raise even though there's no budget_evaluation key at all.
    wrapped({})


# --- record_llm_usage ---------------------------------------------------


def test_record_llm_usage_increments_token_counters():
    before_in = _counter_value(LLM_TOKENS, model="gpt-4o", direction="input")
    before_out = _counter_value(LLM_TOKENS, model="gpt-4o", direction="output")

    record_llm_usage("gpt-4o", {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})

    assert _counter_value(LLM_TOKENS, model="gpt-4o", direction="input") == before_in + 100
    assert _counter_value(LLM_TOKENS, model="gpt-4o", direction="output") == before_out + 20


def test_record_llm_usage_increments_cost_for_a_known_model():
    before = _counter_value(LLM_COST_USD, model="gpt-4o")

    record_llm_usage("gpt-4o", {"input_tokens": 1000, "output_tokens": 1000})

    after = _counter_value(LLM_COST_USD, model="gpt-4o")
    assert after > before  # exact pricing is documented-approximate; just verify it moved


def test_record_llm_usage_is_a_noop_for_none_usage():
    before = _counter_value(LLM_TOKENS, model="gpt-4o", direction="input")
    record_llm_usage("gpt-4o", None)
    assert _counter_value(LLM_TOKENS, model="gpt-4o", direction="input") == before


def test_record_llm_usage_is_a_noop_for_empty_usage():
    before = _counter_value(LLM_TOKENS, model="gpt-4o", direction="input")
    record_llm_usage("gpt-4o", {})
    assert _counter_value(LLM_TOKENS, model="gpt-4o", direction="input") == before


def test_record_llm_usage_still_tracks_tokens_for_an_unpriced_model():
    before_tokens = _counter_value(LLM_TOKENS, model="some-future-model", direction="input")
    record_llm_usage("some-future-model", {"input_tokens": 50, "output_tokens": 10})
    assert _counter_value(LLM_TOKENS, model="some-future-model", direction="input") == (
        before_tokens + 50
    )
    # No pricing entry for this model -> cost series is simply never created/incremented;
    # confirm no exception, which is the only thing that would indicate a bug here.
