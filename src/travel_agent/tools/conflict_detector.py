"""ConflictDetector — Week 6 deliverable.

Validates an Itinerary against five constraint types: overlapping items, travel
times that are physically impossible given real distances, budget overruns,
too many activities crammed into one day, and restaurants scheduled outside normal
meal hours. ItineraryBuilder (Week 5) already avoids most of these by construction,
but this exists as an independent audit layer — useful once itineraries can be
modified after the fact (multi-turn refinement, manual edits) rather than only
ever produced fresh by the builder.
"""

from __future__ import annotations

from datetime import time

from travel_agent.models.core import Conflict, DayPlan, Itinerary
from travel_agent.tools.budget_tracker import estimate_itinerary_cost
from travel_agent.tools.distance_matrix import TravelTimeEstimator

MAX_ACTIVITIES_PER_DAY_DEFAULT = 4
LUNCH_WINDOW = (time(11, 30), time(14, 30))
DINNER_WINDOW = (time(18, 0), time(21, 30))
_ACTIVITY_TYPES = {"attraction", "restaurant"}


class ConflictDetector:
    def __init__(
        self,
        travel_time_estimator: TravelTimeEstimator | None = None,
        max_activities_per_day: int = MAX_ACTIVITIES_PER_DAY_DEFAULT,
    ) -> None:
        self._travel_time = travel_time_estimator or TravelTimeEstimator()
        self._max_activities_per_day = max_activities_per_day

    def detect(self, itinerary: Itinerary) -> list[Conflict]:
        conflicts: list[Conflict] = []
        for day in itinerary.days:
            conflicts += self._detect_overlaps(day)
            conflicts += self._detect_impossible_travel(day)
            conflicts += self._detect_max_activities(day)
            conflicts += self._detect_meal_time_violations(day)
        conflicts += self._detect_budget_overrun(itinerary)
        return conflicts

    def _detect_overlaps(self, day: DayPlan) -> list[Conflict]:
        conflicts = []
        items = sorted(day.items, key=lambda i: i.start_time)
        for a, b in zip(items, items[1:], strict=False):
            if a.end_time > b.start_time:
                conflicts.append(
                    Conflict(
                        day_number=day.day_number,
                        conflict_type="overlap",
                        description=(
                            f"{a.title!r} ({a.start_time.time()}-{a.end_time.time()}) "
                            f"overlaps with {b.title!r} (starts {b.start_time.time()})"
                        ),
                    )
                )
        return conflicts

    def _detect_impossible_travel(self, day: DayPlan) -> list[Conflict]:
        conflicts = []
        items = sorted(day.items, key=lambda i: i.start_time)
        for a, b in zip(items, items[1:], strict=False):
            if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
                continue
            gap_minutes = (b.start_time - a.end_time).total_seconds() / 60
            if gap_minutes < 0:
                continue  # already reported as an overlap
            required = self._travel_time.minutes_between(a.lat, a.lng, b.lat, b.lng)
            if gap_minutes < required:
                conflicts.append(
                    Conflict(
                        day_number=day.day_number,
                        conflict_type="impossible_travel",
                        description=(
                            f"Only {gap_minutes:.0f} min between {a.title!r} and {b.title!r}, "
                            f"but travel takes ~{required} min"
                        ),
                    )
                )
        return conflicts

    def _detect_max_activities(self, day: DayPlan) -> list[Conflict]:
        count = sum(1 for i in day.items if i.activity_type in _ACTIVITY_TYPES)
        if count > self._max_activities_per_day:
            return [
                Conflict(
                    day_number=day.day_number,
                    conflict_type="max_activities_exceeded",
                    description=(
                        f"{count} activities scheduled, exceeding the max of "
                        f"{self._max_activities_per_day}"
                    ),
                )
            ]
        return []

    def _detect_meal_time_violations(self, day: DayPlan) -> list[Conflict]:
        conflicts = []
        for item in day.items:
            if item.activity_type != "restaurant":
                continue
            t = item.start_time.time()
            in_lunch = LUNCH_WINDOW[0] <= t <= LUNCH_WINDOW[1]
            in_dinner = DINNER_WINDOW[0] <= t <= DINNER_WINDOW[1]
            if not (in_lunch or in_dinner):
                conflicts.append(
                    Conflict(
                        day_number=day.day_number,
                        conflict_type="meal_time_violation",
                        description=f"{item.title!r} scheduled at {t}, outside normal meal hours",
                    )
                )
        return conflicts

    def _detect_budget_overrun(self, itinerary: Itinerary) -> list[Conflict]:
        prefs = itinerary.preferences
        if not prefs.budget_total:
            return []
        total = estimate_itinerary_cost(itinerary)
        if total > prefs.budget_total:
            overage = total - prefs.budget_total
            return [
                Conflict(
                    day_number=0,
                    conflict_type="budget_overrun",
                    description=(
                        f"Estimated total {total:.2f} {prefs.budget_currency} exceeds budget "
                        f"of {prefs.budget_total:.2f} by {overage:.2f}"
                    ),
                )
            ]
        return []
