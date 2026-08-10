from datetime import date

import ics

from travel_agent.models.core import DayPlan, Itinerary, ItineraryItem, TravelPreferences
from travel_agent.tools.calendar_export import generate_ics


def _prefs(destination="Paris"):
    return TravelPreferences(destination=destination, raw_text="t")


def _item(
    title,
    activity_type="attraction",
    start="2026-09-01T09:00:00",
    end="2026-09-01T11:00:00",
    location=None,
    description=None,
):
    return ItineraryItem(
        time_slot="morning",
        start_time=start,
        end_time=end,
        activity_type=activity_type,
        title=title,
        location=location,
        description=description,
    )


def _itinerary(days):
    return Itinerary(preferences=_prefs(), days=days)


def test_generates_a_valid_ics_calendar():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    ics_text = generate_ics(_itinerary([day]))
    assert ics_text.startswith("BEGIN:VCALENDAR")
    assert "END:VCALENDAR" in ics_text
    # Round-trips through the same library that produced it — a real,
    # meaningful validity check, not just string matching.
    parsed = ics.Calendar(ics_text)
    assert len(parsed.events) == 1


def test_one_event_per_item_across_all_days():
    day1 = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower"), _item("Bistro", activity_type="restaurant")],
    )
    day2 = DayPlan(day_number=2, date=date(2026, 9, 2), items=[_item("Louvre")])
    ics_text = generate_ics(_itinerary([day1, day2]))
    parsed = ics.Calendar(ics_text)
    assert len(parsed.events) == 3
    assert {e.name for e in parsed.events} == {"Eiffel Tower", "Bistro", "Louvre"}


def test_event_uses_the_items_own_start_and_end_time():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower", start="2026-09-01T09:00:00", end="2026-09-01T11:00:00")],
    )
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    event = next(iter(parsed.events))
    assert event.begin.hour == 9
    assert event.end.hour == 11


def test_event_falls_back_to_destination_when_item_has_no_location():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    event = next(iter(parsed.events))
    assert event.location == "Paris"


def test_event_uses_the_items_own_location_when_present():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower", location="Champ de Mars, Paris")],
    )
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    event = next(iter(parsed.events))
    assert event.location == "Champ de Mars, Paris"


def test_event_description_included_when_present():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Eiffel Tower", description="An iconic iron lattice tower.")],
    )
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    event = next(iter(parsed.events))
    assert event.description == "An iconic iron lattice tower."


def test_event_description_is_none_when_absent():
    day = DayPlan(day_number=1, date=date(2026, 9, 1), items=[_item("Eiffel Tower")])
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    event = next(iter(parsed.events))
    assert event.description is None


def test_empty_itinerary_produces_a_calendar_with_no_events():
    ics_text = generate_ics(_itinerary([DayPlan(day_number=1, date=date(2026, 9, 1), items=[])]))
    parsed = ics.Calendar(ics_text)
    assert len(parsed.events) == 0


def test_zero_duration_item_does_not_raise():
    day = DayPlan(
        day_number=1,
        date=date(2026, 9, 1),
        items=[_item("Quick stop", start="2026-09-01T09:00:00", end="2026-09-01T09:00:00")],
    )
    ics_text = generate_ics(_itinerary([day]))
    parsed = ics.Calendar(ics_text)
    assert len(parsed.events) == 1
