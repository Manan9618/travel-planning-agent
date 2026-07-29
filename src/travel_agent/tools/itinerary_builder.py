"""ItineraryBuilder v1 — Week 5 deliverable.

Assigns flights/hotel/attractions/restaurants into a day-by-day schedule:
- Day 1 (arrival): flight arrival -> transfer to hotel -> check-in -> dinner if time allows
- Middle days (full days): morning attraction, lunch, afternoon attraction, dinner
- Last day (departure): checkout -> transfer to airport

"Opening hours" validation uses fixed, category-appropriate time windows (9am-noon for
morning attractions, etc.) rather than parsing real opening-hours text, since neither
Serper (attractions/restaurants Week 3) nor Booking.com (hotels Week 2) actually supply
that data. Travel time between consecutive activities comes from the real Distance
Matrix API (TravelTimeEstimator); airport transfer times are flat estimates, since we
don't model airport coordinates yet (no round-trip flight object either — see Week 2's
FlightSearchTool notes). Both limitations are candidates for later weeks.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from travel_agent.models.core import (
    Attraction,
    DayPlan,
    FlightOption,
    HotelOption,
    Itinerary,
    ItineraryItem,
    Restaurant,
    TravelPreferences,
)
from travel_agent.tools.distance_matrix import TravelTimeEstimator

HOTEL_CHECKIN_TIME = time(15, 0)
HOTEL_CHECKOUT_TIME = time(11, 0)

MORNING_SLOT = (time(9, 0), time(12, 0))
LUNCH_SLOT = (time(12, 30), time(13, 30))
AFTERNOON_SLOT = (time(14, 0), time(17, 0))
DINNER_SLOT = (time(19, 0), time(20, 30))

ARRIVAL_TRANSFER_MINUTES = 90  # flight arrival -> hotel; flat estimate, no airport coords yet
DEPARTURE_TRANSFER_MINUTES = 60  # hotel checkout -> airport; same limitation
DEFAULT_MEAL_MINUTES = 60
DEFAULT_TRIP_LENGTH_DAYS = 5


def _slot_for_time(t: time) -> str:
    if t.hour < 12:
        return "morning"
    if t.hour < 18:
        return "afternoon"
    return "evening"


class ItineraryBuilder:
    def __init__(self, travel_time_estimator: TravelTimeEstimator | None = None) -> None:
        self._travel_time = travel_time_estimator or TravelTimeEstimator()

    def build(
        self,
        preferences: TravelPreferences,
        hotel: HotelOption,
        attractions: list[Attraction],
        restaurants: list[Restaurant],
        flight: FlightOption | None = None,
    ) -> Itinerary:
        start = preferences.start_date or (date.today() + timedelta(days=30))
        if preferences.end_date:
            end = preferences.end_date
        else:
            duration = preferences.duration_days or DEFAULT_TRIP_LENGTH_DAYS
            end = start + timedelta(days=duration - 1)
        num_days = max((end - start).days + 1, 1)

        days: list[DayPlan] = []
        for day_index in range(num_days):
            current_date = start + timedelta(days=day_index)
            day_number = day_index + 1
            if day_index == 0:
                day_plan = self._build_arrival_day(
                    day_number, current_date, hotel, flight, restaurants, preferences.destination
                )
            elif day_index == num_days - 1:
                day_plan = self._build_departure_day(day_number, current_date, hotel)
            else:
                day_plan = self._build_full_day(
                    day_number, current_date, hotel, attractions, restaurants, day_index
                )
            days.append(day_plan)

        return Itinerary(
            preferences=preferences,
            days=days,
            flights=[flight] if flight else [],
            hotel=hotel,
        )

    # --- day builders ------------------------------------------------------

    def _build_arrival_day(
        self,
        day_number: int,
        current_date: date,
        hotel: HotelOption,
        flight: FlightOption | None,
        restaurants: list[Restaurant],
        destination: str,
    ) -> DayPlan:
        items: list[ItineraryItem] = []

        if flight is not None:
            # TravelPayouts returns the cheapest fare found near the requested
            # month, not necessarily on the requested date (see FlightSearchTool
            # notes) — its date component can't be trusted to match this trip's
            # actual Day 1. Only the time-of-day is meaningful, so it's anchored
            # to the itinerary's real start date rather than the flight's own date.
            arrival_dt = datetime.combine(current_date, flight.arrival_time.time())
            items.append(
                ItineraryItem(
                    time_slot=_slot_for_time(arrival_dt.time()),
                    start_time=arrival_dt,
                    end_time=arrival_dt,
                    activity_type="flight",
                    title=f"Arrive in {destination}",
                    cost=flight.price,
                )
            )
            transfer_end = arrival_dt + timedelta(minutes=ARRIVAL_TRANSFER_MINUTES)
            items.append(
                ItineraryItem(
                    time_slot=_slot_for_time(arrival_dt.time()),
                    start_time=arrival_dt,
                    end_time=transfer_end,
                    activity_type="transfer",
                    title="Transfer to hotel",
                    notes="Estimated; airport coordinates aren't modeled yet",
                )
            )
            checkin_start = max(transfer_end, datetime.combine(current_date, HOTEL_CHECKIN_TIME))
        else:
            checkin_start = datetime.combine(current_date, HOTEL_CHECKIN_TIME)

        items.append(
            ItineraryItem(
                time_slot=_slot_for_time(checkin_start.time()),
                start_time=checkin_start,
                end_time=checkin_start,
                activity_type="hotel_checkin",
                title=f"Check in to {hotel.name}",
                location=hotel.address,
                lat=hotel.lat,
                lng=hotel.lng,
            )
        )

        dinner = self._pick(restaurants, 0)
        if dinner and checkin_start.time() < DINNER_SLOT[1]:
            start, end = self._next_slot(
                checkin_start,
                hotel.lat,
                hotel.lng,
                dinner.lat,
                dinner.lng,
                *DINNER_SLOT,
                current_date,
                DEFAULT_MEAL_MINUTES,
            )
            if start is not None:
                items.append(
                    ItineraryItem(
                        time_slot="evening",
                        start_time=start,
                        end_time=end,
                        activity_type="restaurant",
                        title=dinner.name,
                        lat=dinner.lat,
                        lng=dinner.lng,
                    )
                )

        return DayPlan(day_number=day_number, date=current_date, items=items)

    def _build_full_day(
        self,
        day_number: int,
        current_date: date,
        hotel: HotelOption,
        attractions: list[Attraction],
        restaurants: list[Restaurant],
        day_index: int,
    ) -> DayPlan:
        items: list[ItineraryItem] = []
        prev_end = datetime.combine(current_date, time(8, 0))
        prev_lat, prev_lng = hotel.lat, hotel.lng

        morning = self._pick(attractions, day_index * 2)
        if morning:
            start, end = self._next_slot(
                prev_end,
                prev_lat,
                prev_lng,
                morning.lat,
                morning.lng,
                *MORNING_SLOT,
                current_date,
                morning.estimated_visit_minutes,
            )
            if start is not None:
                items.append(
                    ItineraryItem(
                        time_slot="morning",
                        start_time=start,
                        end_time=end,
                        activity_type="attraction",
                        title=morning.name,
                        location=morning.description,
                        lat=morning.lat,
                        lng=morning.lng,
                        cost=morning.price,
                    )
                )
                prev_end, prev_lat, prev_lng = end, morning.lat, morning.lng

        lunch = self._pick(restaurants, day_index * 2)
        if lunch:
            start, end = self._next_slot(
                prev_end,
                prev_lat,
                prev_lng,
                lunch.lat,
                lunch.lng,
                *LUNCH_SLOT,
                current_date,
                DEFAULT_MEAL_MINUTES,
            )
            if start is not None:
                items.append(
                    ItineraryItem(
                        time_slot="afternoon",
                        start_time=start,
                        end_time=end,
                        activity_type="restaurant",
                        title=lunch.name,
                        lat=lunch.lat,
                        lng=lunch.lng,
                    )
                )
                prev_end, prev_lat, prev_lng = end, lunch.lat, lunch.lng

        afternoon = self._pick(attractions, day_index * 2 + 1)
        if afternoon:
            start, end = self._next_slot(
                prev_end,
                prev_lat,
                prev_lng,
                afternoon.lat,
                afternoon.lng,
                *AFTERNOON_SLOT,
                current_date,
                afternoon.estimated_visit_minutes,
            )
            if start is not None:
                items.append(
                    ItineraryItem(
                        time_slot="afternoon",
                        start_time=start,
                        end_time=end,
                        activity_type="attraction",
                        title=afternoon.name,
                        location=afternoon.description,
                        lat=afternoon.lat,
                        lng=afternoon.lng,
                        cost=afternoon.price,
                    )
                )
                prev_end, prev_lat, prev_lng = end, afternoon.lat, afternoon.lng

        dinner = self._pick(restaurants, day_index * 2 + 1)
        if dinner:
            start, end = self._next_slot(
                prev_end,
                prev_lat,
                prev_lng,
                dinner.lat,
                dinner.lng,
                *DINNER_SLOT,
                current_date,
                DEFAULT_MEAL_MINUTES,
            )
            if start is not None:
                items.append(
                    ItineraryItem(
                        time_slot="evening",
                        start_time=start,
                        end_time=end,
                        activity_type="restaurant",
                        title=dinner.name,
                        lat=dinner.lat,
                        lng=dinner.lng,
                    )
                )

        return DayPlan(day_number=day_number, date=current_date, items=items)

    def _build_departure_day(
        self, day_number: int, current_date: date, hotel: HotelOption
    ) -> DayPlan:
        checkout_dt = datetime.combine(current_date, HOTEL_CHECKOUT_TIME)
        transfer_end = checkout_dt + timedelta(minutes=DEPARTURE_TRANSFER_MINUTES)
        items = [
            ItineraryItem(
                time_slot="morning",
                start_time=checkout_dt,
                end_time=checkout_dt,
                activity_type="hotel_checkout",
                title=f"Check out of {hotel.name}",
                location=hotel.address,
                lat=hotel.lat,
                lng=hotel.lng,
            ),
            ItineraryItem(
                time_slot="morning",
                start_time=checkout_dt,
                end_time=transfer_end,
                activity_type="transfer",
                title="Transfer to airport",
                notes="Estimated; airport coordinates aren't modeled yet",
            ),
        ]
        return DayPlan(day_number=day_number, date=current_date, items=items)

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _pick(items: list, index: int):
        if not items:
            return None
        return items[index % len(items)]

    def _next_slot(
        self,
        prev_end: datetime,
        prev_lat: float,
        prev_lng: float,
        dest_lat: float,
        dest_lng: float,
        slot_start_t: time,
        slot_end_t: time,
        current_date: date,
        duration_minutes: int,
    ) -> tuple[datetime | None, datetime | None]:
        """Earliest the next activity can start, respecting both its fixed time
        window and travel time from the previous location. Returns (None, None)
        if it can't fit in the window at all; compresses the visit to fit the
        window if travel time eats into (but doesn't exceed) it.
        """
        slot_start_dt = datetime.combine(current_date, slot_start_t)
        slot_end_dt = datetime.combine(current_date, slot_end_t)
        travel_minutes = self._travel_time.minutes_between(prev_lat, prev_lng, dest_lat, dest_lng)
        earliest_arrival = prev_end + timedelta(minutes=travel_minutes)

        start = max(slot_start_dt, earliest_arrival)
        if start >= slot_end_dt:
            return None, None
        end = min(start + timedelta(minutes=duration_minutes), slot_end_dt)
        return start, end
