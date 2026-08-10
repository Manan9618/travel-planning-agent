"""CalendarExportTool — generates a downloadable .ics file from a built
Itinerary. Pure computation, no external API, same scoping as
`budget_tracker.py`.

One VEVENT per scheduled `ItineraryItem` (flight/hotel_checkin/attraction/
restaurant/transfer), using its real `start_time`/`end_time`, `title`,
`location`, and `description` (attraction items only, same field
`enrich_attractions` already fills in for the PDF) — importable into
Google Calendar, Apple Calendar, Outlook, or any other RFC 5545 client.
Uses the `ics` library rather than hand-rolling RFC 5545's line-folding
and field-escaping rules, which real calendar apps are notoriously picky
about getting exactly right.
"""

from __future__ import annotations

from ics import Calendar, Event

from travel_agent.models.core import Itinerary


def generate_ics(itinerary: Itinerary) -> str:
    calendar = Calendar()
    destination = itinerary.preferences.destination
    for day in itinerary.days:
        for item in day.items:
            calendar.events.add(
                Event(
                    name=item.title,
                    begin=item.start_time,
                    # Defensive against a malformed/hand-built Itinerary
                    # (e.g. in a test) where end_time precedes start_time —
                    # the `ics` library raises rather than accepting a
                    # negative-duration event.
                    end=max(item.end_time, item.start_time),
                    location=item.location or destination,
                    description=item.description or None,
                )
            )
    return calendar.serialize()
