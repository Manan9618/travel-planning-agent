from datetime import date

from travel_agent.models.core import DayPlan, HotelOption, Itinerary, TravelPreferences
from travel_agent.tools.itinerary_narrator import ItineraryNarrator


def _itinerary() -> Itinerary:
    prefs = TravelPreferences(destination="Paris", start_date=date(2026, 9, 1), raw_text="t")
    hotel = HotelOption(name="Hotel", address="Paris", lat=48.85, lng=2.35, price_per_night=100)
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[])
    return Itinerary(preferences=prefs, days=[day], hotel=hotel)


class _FakeChunk:
    def __init__(self, content: str):
        self.content = content


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
