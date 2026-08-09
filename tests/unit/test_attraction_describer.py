from types import SimpleNamespace
from unittest.mock import MagicMock

from travel_agent.tools.attraction_describer import (
    AttractionDescriberTool,
    _AttractionDescription,
    _AttractionDescriptions,
)


def _tool(fake_cache):
    tool = AttractionDescriberTool(cache=fake_cache)
    return tool


def _fake_response(pairs):
    return _AttractionDescriptions(
        attractions=[_AttractionDescription(title=t, description=d) for t, d in pairs]
    )


# --- empty input ----------------------------------------------------------


def test_describe_returns_empty_dict_for_no_titles(fake_cache):
    tool = _tool(fake_cache)
    assert tool.describe([], "Paris") == {}


def test_describe_deduplicates_titles(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    seen = []
    monkeypatch.setattr(tool, "_fetch", lambda titles, dest: (seen.extend(titles), {})[1])
    tool.describe(["Eiffel Tower", "Eiffel Tower", "Louvre"], "Paris")
    assert seen == ["Eiffel Tower", "Louvre"]


# --- happy path -------------------------------------------------------------


def test_describe_returns_fetched_descriptions(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    monkeypatch.setattr(
        tool, "_fetch", lambda titles, dest: {"Eiffel Tower": "An iconic iron lattice tower."}
    )
    result = tool.describe(["Eiffel Tower"], "Paris")
    assert result == {"Eiffel Tower": "An iconic iron lattice tower."}


def test_describe_passes_destination_through(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    seen_dest = []
    monkeypatch.setattr(tool, "_fetch", lambda titles, dest: (seen_dest.append(dest), {})[1])
    tool.describe(["Eiffel Tower"], "Paris")
    assert seen_dest == ["Paris"]


# --- caching ----------------------------------------------------------------


def test_second_call_for_same_title_does_not_refetch(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    calls = []
    monkeypatch.setattr(
        tool,
        "_fetch",
        lambda titles, dest: (calls.append(titles), {"Eiffel Tower": "desc"})[1],
    )
    tool.describe(["Eiffel Tower"], "Paris")
    tool.describe(["Eiffel Tower"], "Paris")
    assert len(calls) == 1


def test_only_uncached_titles_are_fetched(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    tool._cache.set(tool._cache_key("Eiffel Tower", "Paris"), "already cached", 3600)
    seen = []
    monkeypatch.setattr(tool, "_fetch", lambda titles, dest: (seen.extend(titles), {})[1])
    result = tool.describe(["Eiffel Tower", "Louvre"], "Paris")
    assert seen == ["Louvre"]
    assert result["Eiffel Tower"] == "already cached"


def test_empty_fetch_result_is_cached_as_empty_string(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    monkeypatch.setattr(tool, "_fetch", lambda titles, dest: {})
    tool.describe(["Eiffel Tower"], "Paris")
    assert fake_cache.get(tool._cache_key("Eiffel Tower", "Paris")) == ""


# --- graceful degradation on LLM failure ------------------------------------


def test_fetch_returns_empty_dict_when_llm_raises(fake_cache):
    tool = _tool(fake_cache)
    tool._llm = MagicMock()
    tool._llm.invoke.side_effect = RuntimeError("openai down")
    assert tool._fetch(["Eiffel Tower"], "Paris") == {}


def test_fetch_returns_empty_dict_on_malformed_response(fake_cache):
    tool = _tool(fake_cache)
    tool._llm = MagicMock()
    tool._llm.invoke.return_value = "not a structured response"
    assert tool._fetch(["Eiffel Tower"], "Paris") == {}


def test_fetch_maps_titles_to_descriptions(fake_cache):
    tool = _tool(fake_cache)
    tool._llm = MagicMock()
    tool._llm.invoke.return_value = {
        "raw": SimpleNamespace(usage_metadata=None),
        "parsed": _fake_response([("Eiffel Tower", "desc 1"), ("Louvre", "desc 2")]),
    }
    result = tool._fetch(["Eiffel Tower", "Louvre"], "Paris")
    assert result == {"Eiffel Tower": "desc 1", "Louvre": "desc 2"}


def test_describe_gracefully_skips_titles_the_llm_did_not_return(fake_cache, monkeypatch):
    tool = _tool(fake_cache)
    monkeypatch.setattr(tool, "_fetch", lambda titles, dest: {"Eiffel Tower": "desc"})
    result = tool.describe(["Eiffel Tower", "Louvre"], "Paris")
    assert result == {"Eiffel Tower": "desc"}
    assert "Louvre" not in result
