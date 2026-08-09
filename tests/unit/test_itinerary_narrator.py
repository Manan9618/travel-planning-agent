from datetime import date

from travel_agent.models.core import DayPlan, HotelOption, Itinerary, TravelPreferences
from travel_agent.tools.itinerary_narrator import ItineraryNarrator


def _itinerary() -> Itinerary:
    prefs = TravelPreferences(destination="Paris", start_date=date(2026, 9, 1), raw_text="t")
    hotel = HotelOption(name="Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100)
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[])
    return Itinerary(preferences=prefs, days=[day], hotel=hotel)


class _FakeChunk:
    """Mirrors the two bits of a real AIMessageChunk narrate() relies on:
    .content and `+` accumulation (Week 19's cost tracking builds up the
    full response, including usage_metadata, by summing streamed chunks)."""

    def __init__(self, content: str, usage_metadata: dict | None = None):
        self.content = content
        self.usage_metadata = usage_metadata

    def __add__(self, other: "_FakeChunk") -> "_FakeChunk":
        return _FakeChunk(self.content + other.content, other.usage_metadata or self.usage_metadata)


class _FakeStreamingLLM:
    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def astream(self, messages):
        for chunk in self._chunks:
            yield _FakeChunk(chunk)


async def test_narrate_yields_each_token_in_order():
    narrator = ItineraryNarrator()
    narrator._llm = _FakeStreamingLLM(["Bonjour", ", ", "Paris", "!"])
    tokens = [t async for t in narrator.narrate(_itinerary())]
    assert tokens == ["Bonjour", ", ", "Paris", "!"]


async def test_narrate_skips_empty_chunks():
    narrator = ItineraryNarrator()
    narrator._llm = _FakeStreamingLLM(["Hello", "", " world"])
    tokens = [t async for t in narrator.narrate(_itinerary())]
    assert tokens == ["Hello", " world"]


async def test_narrate_passes_itinerary_summary_to_the_llm():
    captured = {}

    class _CapturingLLM:
        async def astream(self, messages):
            captured["messages"] = messages
            yield _FakeChunk("ok")

    narrator = ItineraryNarrator()
    narrator._llm = _CapturingLLM()
    _ = [t async for t in narrator.narrate(_itinerary())]
    human_message = captured["messages"][1]
    assert human_message[0] == "human"
    assert "Paris" in human_message[1]


async def test_narrate_records_llm_usage_from_accumulated_chunks(monkeypatch):
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    narrator = ItineraryNarrator()
    narrator._llm = _FakeStreamingLLMWithUsage(["Bonjour", "!"], usage)

    recorded = {}
    monkeypatch.setattr(
        "travel_agent.tools.itinerary_narrator.record_llm_usage",
        lambda model, u: recorded.update(model=model, usage=u),
    )

    _ = [t async for t in narrator.narrate(_itinerary())]

    assert recorded["usage"] == usage
    assert recorded["model"] == narrator._model


class _FakeStreamingLLMWithUsage:
    def __init__(self, chunks: list[str], usage: dict) -> None:
        self._chunks = chunks
        self._usage = usage

    async def astream(self, messages):
        for i, chunk in enumerate(self._chunks):
            is_last = i == len(self._chunks) - 1
            yield _FakeChunk(chunk, usage_metadata=self._usage if is_last else None)
