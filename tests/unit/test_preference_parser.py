from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from travel_agent.models.core import BudgetTier, Pace, TravelPreferences, TripStyle
from travel_agent.tools.preference_parser import PreferenceParser, _ParsedFields


class _FakeSemanticCache:
    """Always-miss stand-in - `_invoke`'s real path calls
    `self._embeddings.embed_query(...)` (a real OpenAI network call) before
    ever touching the semantic cache, so any test that exercises `_invoke`
    directly (rather than monkeypatching it away entirely) needs this to
    avoid making that call with the dummy test API key."""

    def get(self, text, guard=""):
        return None

    def set(self, text, value, guard=""):
        pass


def _parser() -> PreferenceParser:
    return PreferenceParser(semantic_cache=_FakeSemanticCache())


def _parser_with_result(monkeypatch, fields: _ParsedFields) -> PreferenceParser:
    parser = _parser()
    monkeypatch.setattr(parser, "_invoke", lambda text, reference_date: fields)
    return parser


def _minimal_fields(**overrides) -> _ParsedFields:
    defaults = {"destination": "Paris"}
    defaults.update(overrides)
    return _ParsedFields(**defaults)


# --- input validation ---------------------------------------------------


def test_parse_rejects_empty_string():
    parser = PreferenceParser()
    with pytest.raises(ValueError):
        parser.parse("")


def test_parse_rejects_whitespace_only():
    parser = PreferenceParser()
    with pytest.raises(ValueError):
        parser.parse("   ")


def test_parse_rejects_none_like_falsy():
    parser = PreferenceParser()
    with pytest.raises(ValueError):
        parser.parse(None)  # type: ignore[arg-type]


def test_parse_raises_value_error_when_llm_returns_no_destination(monkeypatch):
    # Regression: _ParsedFields.destination became optional (needed for
    # parse_partial()), so parse() must enforce it explicitly rather than
    # relying on pydantic to reject a missing required field.
    parser = _parser_with_result(monkeypatch, _ParsedFields())
    with pytest.raises(ValueError, match="destination"):
        parser.parse("more outdoor activities")


# --- basic pass-through of fields ---------------------------------------


def test_parse_returns_travel_preferences_instance(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse("I want to go to Paris")
    assert isinstance(result, TravelPreferences)


def test_parse_preserves_raw_text_exactly(monkeypatch):
    text = "I want to visit Paris for 5 days in July under $3000"
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse(text)
    assert result.raw_text == text


def test_parse_passes_through_destination(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields(destination="Tokyo"))
    result = parser.parse("tokyo please")
    assert result.destination == "Tokyo"


def test_parse_passes_through_origin(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields(origin="New York"))
    result = parser.parse("from NYC to Paris")
    assert result.origin == "New York"


def test_parse_origin_defaults_to_none(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse("Paris trip")
    assert result.origin is None


def test_parse_passes_through_dates(monkeypatch):
    fields = _minimal_fields(start_date=date(2026, 7, 1), end_date=date(2026, 7, 5))
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris in July")
    assert result.start_date == date(2026, 7, 1)
    assert result.end_date == date(2026, 7, 5)


def test_parse_infers_duration_from_dates(monkeypatch):
    fields = _minimal_fields(start_date=date(2026, 7, 1), end_date=date(2026, 7, 5))
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris for 5 days in July")
    assert result.duration_days == 5


def test_parse_passes_through_explicit_duration(monkeypatch):
    fields = _minimal_fields(duration_days=7)
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("a week in Paris")
    assert result.duration_days == 7


def test_parse_passes_through_budget_total(monkeypatch):
    fields = _minimal_fields(budget_total=3000)
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris under $3000")
    assert result.budget_total == 3000


def test_parse_budget_currency_defaults_usd(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse("Paris trip")
    assert result.budget_currency == "USD"


def test_parse_passes_through_budget_currency(monkeypatch):
    fields = _minimal_fields(budget_currency="EUR")
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris trip, budget in euros")
    assert result.budget_currency == "EUR"


def test_parse_passes_through_budget_tier(monkeypatch):
    fields = _minimal_fields(budget_tier=BudgetTier.LUXURY)
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("a luxury trip to Paris")
    assert result.budget_tier == BudgetTier.LUXURY


def test_parse_passes_through_trip_style(monkeypatch):
    fields = _minimal_fields(trip_style=TripStyle.HONEYMOON)
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("honeymoon in Paris")
    assert result.trip_style == TripStyle.HONEYMOON


def test_parse_pace_defaults_to_moderate(monkeypatch):
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse("Paris trip")
    assert result.pace == Pace.MODERATE


def test_parse_passes_through_travelers_when_unspecified_still_defaults_to_one(monkeypatch):
    # Regression: _ParsedFields.travelers used to default to 1 (a concrete
    # value, not None), so parse() had to keep working even once travelers
    # is genuinely absent from the LLM's structured output.
    parser = _parser_with_result(monkeypatch, _minimal_fields())
    result = parser.parse("Paris trip")
    assert result.travelers == 1


def test_parsed_fields_travelers_budget_currency_pace_default_to_none():
    # Regression (Week 21): these three used to default to a concrete value
    # (1/"USD"/MODERATE) on _ParsedFields itself, making parse_partial()'s
    # output indistinguishable between "the LLM said this" and "the LLM
    # found nothing, the default filled in" - which meant /refine's
    # updates filter could never exclude them, silently resetting all
    # three on every single refinement regardless of what it was about.
    fields = _minimal_fields()
    assert fields.travelers is None
    assert fields.budget_currency is None
    assert fields.pace is None


def test_parse_passes_through_interests(monkeypatch):
    fields = _minimal_fields(interests=["art", "food"])
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris, love art and food")
    assert result.interests == ["art", "food"]


def test_parse_passes_through_must_see(monkeypatch):
    fields = _minimal_fields(must_see=["Eiffel Tower"])
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris, must see the Eiffel Tower")
    assert result.must_see == ["Eiffel Tower"]


def test_parse_passes_through_dietary_restrictions(monkeypatch):
    fields = _minimal_fields(dietary_restrictions=["vegetarian"])
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris, I'm vegetarian")
    assert result.dietary_restrictions == ["vegetarian"]


def test_parse_passes_through_accessibility_needs(monkeypatch):
    fields = _minimal_fields(accessibility_needs=["wheelchair accessible"])
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris, need wheelchair accessible routes")
    assert result.accessibility_needs == ["wheelchair accessible"]


def test_parse_passes_through_priority_weights(monkeypatch):
    fields = _minimal_fields(priority_weights={"accommodation": 0.5, "dining": 0.5})
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Paris, I prioritize accommodation and dining equally")
    assert result.priority_weights == {"accommodation": 0.5, "dining": 0.5}


def test_parse_passes_through_travelers_count(monkeypatch):
    fields = _minimal_fields(travelers=4)
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("family of 4 to Paris")
    assert result.travelers == 4


# --- reference date handling ---------------------------------------------


def test_parse_uses_today_when_no_reference_date_given(monkeypatch):
    captured = {}

    def fake_invoke(text, reference_date):
        captured["reference_date"] = reference_date
        return _minimal_fields()

    parser = PreferenceParser()
    monkeypatch.setattr(parser, "_invoke", fake_invoke)
    parser.parse("Paris trip")
    assert captured["reference_date"] == date.today()


def test_parse_uses_explicit_reference_date(monkeypatch):
    captured = {}

    def fake_invoke(text, reference_date):
        captured["reference_date"] = reference_date
        return _minimal_fields()

    parser = PreferenceParser()
    monkeypatch.setattr(parser, "_invoke", fake_invoke)
    ref = date(2026, 1, 1)
    parser.parse("Paris trip", reference_date=ref)
    assert captured["reference_date"] == ref


# --- retry / error handling on the underlying LLM call --------------------


def test_invoke_retries_on_transient_failure_then_succeeds(monkeypatch):
    parser = _parser()
    good_result = _minimal_fields()
    good_response = {"raw": SimpleNamespace(usage_metadata=None), "parsed": good_result}
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = [RuntimeError("timeout"), RuntimeError("timeout"), good_response]
    monkeypatch.setattr(parser, "_llm", mock_llm)

    result = parser._invoke("Paris trip", date.today())

    assert result == good_result
    assert mock_llm.invoke.call_count == 3


def test_invoke_raises_after_exhausting_retries(monkeypatch):
    parser = _parser()
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("down")
    monkeypatch.setattr(parser, "_llm", mock_llm)

    with pytest.raises(RuntimeError):
        parser._invoke("Paris trip", date.today())

    assert mock_llm.invoke.call_count == 3


def test_invoke_raises_value_error_on_unstructured_response(monkeypatch):
    parser = _parser()
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = {"not": "structured"}
    monkeypatch.setattr(parser, "_llm", mock_llm)

    with pytest.raises(ValueError):
        parser._invoke("Paris trip", date.today())


# --- semantic cache integration (Week 20) ----------------------------------


class _RecordingSemanticCache:
    def __init__(self, hit=None):
        self._hit = hit
        self.get_calls = []
        self.set_calls = []

    def get(self, text, guard=""):
        self.get_calls.append((text, guard))
        return self._hit

    def set(self, text, value, guard=""):
        self.set_calls.append((text, value, guard))


def test_invoke_skips_llm_entirely_on_semantic_cache_hit(monkeypatch):
    hit = _minimal_fields(destination="Paris").model_dump(mode="json")
    parser = PreferenceParser(semantic_cache=_RecordingSemanticCache(hit=hit))
    mock_llm = MagicMock()
    monkeypatch.setattr(parser, "_llm", mock_llm)

    result = parser._invoke("a five-day Paris trip", date(2026, 1, 1))

    assert result.destination == "Paris"
    mock_llm.invoke.assert_not_called()


def test_invoke_populates_semantic_cache_on_miss(monkeypatch):
    cache = _RecordingSemanticCache(hit=None)
    parser = PreferenceParser(semantic_cache=cache)
    good_result = _minimal_fields()
    good_response = {"raw": SimpleNamespace(usage_metadata=None), "parsed": good_result}
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = good_response
    monkeypatch.setattr(parser, "_llm", mock_llm)

    parser._invoke("Paris trip", date(2026, 1, 1))

    assert len(cache.set_calls) == 1
    text, value, guard = cache.set_calls[0]
    assert text == "Paris trip"
    assert value["destination"] == "Paris"
    assert guard == "2026-01-01::paris"


def test_cache_guard_matches_across_reworded_paraphrases():
    guard_a = PreferenceParser._cache_guard("5 days in Paris under $3000", date(2026, 1, 1))
    guard_b = PreferenceParser._cache_guard("$3000 for 5 days, Paris", date(2026, 1, 1))
    assert guard_a == guard_b


def test_cache_guard_differs_on_a_different_budget():
    guard_a = PreferenceParser._cache_guard("5 days in Paris under $3000", date(2026, 1, 1))
    guard_c = PreferenceParser._cache_guard("5 days in Paris under $1000", date(2026, 1, 1))
    assert guard_a != guard_c


def test_cache_guard_differs_on_a_different_reference_date():
    guard_a = PreferenceParser._cache_guard("5 days in Paris under $3000", date(2026, 1, 1))
    guard_d = PreferenceParser._cache_guard("5 days in Paris under $3000", date(2026, 1, 2))
    assert guard_a != guard_d


def test_cache_guard_differs_on_a_different_destination():
    # Real bug this guards against (Week 20 live-testing): whole-text
    # embedding similarity alone scored these two requests at ~0.78 cosine
    # similarity - close enough to a genuine paraphrase's ~0.82 that
    # similarity alone can't be trusted to tell "same trip, reworded" from
    # "different destination, same budget" apart.
    guard_paris = PreferenceParser._cache_guard("5 days in Paris under $3000", date(2026, 1, 1))
    guard_tokyo = PreferenceParser._cache_guard("5 days in Tokyo under $3000", date(2026, 1, 1))
    assert guard_paris != guard_tokyo


def test_parse_end_to_end_with_full_scenario(monkeypatch):
    fields = _minimal_fields(
        destination="Paris",
        origin="Boston",
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 14),
        budget_total=3000,
        travelers=2,
        trip_style=TripStyle.CITY,
        interests=["museums", "food"],
    )
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse("Two of us want 5 days in Paris in July from Boston, under $3000")

    assert result.destination == "Paris"
    assert result.origin == "Boston"
    assert result.duration_days == 5
    assert result.budget_total == 3000
    assert result.travelers == 2
    assert result.trip_style == TripStyle.CITY
    assert result.interests == ["museums", "food"]


# --- parse_partial (used by /refine) --------------------------------------


def test_parse_partial_rejects_empty_string():
    parser = PreferenceParser()
    with pytest.raises(ValueError):
        parser.parse_partial("")


def test_parse_partial_does_not_require_a_destination(monkeypatch):
    # The real bug this covers: a refinement like "more outdoor activities"
    # gives the LLM nothing to infer a destination from, and it correctly
    # leaves the field blank per its own system-prompt instructions. That
    # used to make the underlying structured-output call itself raise a
    # pydantic ValidationError (destination was a required field), an
    # unhandled crash. parse_partial() must tolerate this and just return
    # whatever else was found.
    parser = _parser_with_result(monkeypatch, _ParsedFields(interests=["outdoor activities"]))
    result = parser.parse_partial("more outdoor activities")
    assert result["destination"] is None
    assert result["interests"] == ["outdoor activities"]


def test_parse_partial_returns_a_plain_json_safe_dict(monkeypatch):
    fields = _minimal_fields(destination="Paris", start_date=date(2026, 7, 1))
    parser = _parser_with_result(monkeypatch, fields)
    result = parser.parse_partial("Paris in July")
    assert isinstance(result, dict)
    assert result["destination"] == "Paris"
    assert result["start_date"] == "2026-07-01"  # JSON-safe, not a date object


def test_parse_partial_uses_today_when_no_reference_date_given(monkeypatch):
    captured = {}

    def fake_invoke(text, reference_date):
        captured["reference_date"] = reference_date
        return _minimal_fields()

    parser = PreferenceParser()
    monkeypatch.setattr(parser, "_invoke", fake_invoke)
    parser.parse_partial("less walking")
    assert captured["reference_date"] == date.today()
