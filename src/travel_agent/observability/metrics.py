"""Prometheus metrics (Week 19).

`instrument_node` wraps a single LangGraph node with call-count and
duration tracking; applied once per node at graph-build time
(`agents/graph.py`'s `build_planning_graph`) rather than inside each of the
~12 node factories in `nodes.py`, so instrumenting a new step never means
touching its own function. Every node already reports success/failure via
its own `errors` list (the same signal the supervisor already reads) —
`instrument_node` reuses that as the metric label rather than inventing a
second way to ask "did this step fail".

`record_llm_usage` is called from each LLM call site (PreferenceParser,
AttractionDescriberTool, ItineraryJudge, ItineraryNarrator) after a real
response comes back, given LangChain's standardized `usage_metadata` shape
(`{"input_tokens": int, "output_tokens": int, "total_tokens": int}`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from prometheus_client import Counter, Histogram

PLANNING_STEP_CALLS = Counter(
    "planning_step_calls_total",
    "LangGraph planning-step invocations, by step and outcome",
    ["step", "status"],
)
PLANNING_STEP_DURATION = Histogram(
    "planning_step_duration_seconds",
    "Wall-clock time per planning step",
    ["step"],
)
PLANNING_DURATION = Histogram(
    "planning_duration_seconds",
    "Wall-clock time for a full planning run (graph.stream start to terminal)",
    buckets=(1, 2, 5, 10, 20, 30, 60, 120, 180, 300),
)
BUDGET_ADHERENCE = Histogram(
    "budget_adherence_score",
    "BudgetEvaluation.adherence_score distribution (1.0 = exact match to stated budget)",
    buckets=tuple(i / 10 for i in range(11)),
)
LLM_TOKENS = Counter(
    "llm_tokens_total",
    "LLM tokens consumed, by model and direction",
    ["model", "direction"],  # direction: input | output
)
# Approximate — see _MODEL_PRICING_USD_PER_1K_TOKENS docstring below. OpenAI's
# own invoice is the source of billing truth; this is a live, in-app estimate.
LLM_COST_USD = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD, by model (approximate — see source)",
    ["model"],
)

# As-of-writing (2026) public per-1K-token USD pricing for the models this
# project actually uses. OpenAI's pricing page is the source of truth and
# does change over time; treat this as a reasonable estimate for relative
# cost tracking across sessions, not a billing-accurate figure. Unknown
# models are simply not cost-tracked (tokens still are, via LLM_TOKENS).
_MODEL_PRICING_USD_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
}


def instrument_node(step_name: str, node: Callable[[dict], dict]) -> Callable[[dict], dict]:
    def wrapped(state: dict) -> dict:
        start = time.monotonic()
        result = node(state)
        PLANNING_STEP_DURATION.labels(step=step_name).observe(time.monotonic() - start)
        status = "error" if result.get("errors") else "success"
        PLANNING_STEP_CALLS.labels(step=step_name, status=status).inc()

        if step_name == "optimize_budget":
            evaluation = result.get("budget_evaluation")
            if evaluation and evaluation.get("adherence_score") is not None:
                BUDGET_ADHERENCE.observe(evaluation["adherence_score"])

        return result

    return wrapped


def record_llm_usage(model: str, usage: dict[str, Any] | None) -> None:
    if not usage:
        return
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    if input_tokens:
        LLM_TOKENS.labels(model=model, direction="input").inc(input_tokens)
    if output_tokens:
        LLM_TOKENS.labels(model=model, direction="output").inc(output_tokens)

    pricing = _MODEL_PRICING_USD_PER_1K_TOKENS.get(model)
    if pricing:
        cost = (input_tokens / 1000) * pricing["input"] + (output_tokens / 1000) * pricing["output"]
        if cost:
            LLM_COST_USD.labels(model=model).inc(cost)
