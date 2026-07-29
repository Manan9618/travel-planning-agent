"""ConflictResolver — Week 6 deliverable.

Attempts to automatically fix each conflict ConflictDetector reports: shifting
times, dropping the lowest-priority activity, or trimming optional-cost items.
Budget overruns are only resolved if trimming optional attractions/restaurants is
enough — if fixed costs (flights, hotel) alone exceed the budget, that conflict is
returned unresolved for a human decision (see agents/nodes.py's human_review step).
Every attempt, successful or not, is logged (both via `logging` and the returned
ResolutionLogEntry list) for later evaluation analysis.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta

from travel_agent.models.core import Conflict, DayPlan, Itinerary, ResolutionLogEntry
from travel_agent.tools.budget_tracker import estimate_itinerary_cost
from travel_agent.tools.conflict_detector import DINNER_WINDOW, LUNCH_WINDOW, ConflictDetector
from travel_agent.tools.distance_matrix import TravelTimeEstimator

logger = logging.getLogger(__name__)

_ACTIVITY_TYPES = {"attraction", "restaurant"}
_LUNCH_TARGET = time(13, 0)
_DINNER_TARGET = time(19, 30)


class ConflictResolver:
    def __init__(
        self,
        travel_time_estimator: TravelTimeEstimator | None = None,
        max_activities_per_day: int = 4,
    ) -> None:
        self._travel_time = travel_time_estimator or TravelTimeEstimator()
        self._max_activities_per_day = max_activities_per_day

    def resolve(
        self, itinerary: Itinerary, conflicts: list[Conflict]
    ) -> tuple[Itinerary, list[ResolutionLogEntry], list[Conflict]]:
        itinerary = itinerary.model_copy(deep=True)
        log: list[ResolutionLogEntry] = []
        unresolved: list[Conflict] = []

        strategies = {
            "overlap": self._resolve_overlap,
            "impossible_travel": self._resolve_impossible_travel,
            "max_activities_exceeded": self._resolve_max_activities,
            "meal_time_violation": self._resolve_meal_time,
            "budget_overrun": self._resolve_budget_overrun,
        }

        for conflict in conflicts:
            strategy = strategies.get(conflict.conflict_type)
            if strategy is None:
                action, resolved = "no resolution strategy for this conflict type", False
            else:
                action, resolved = strategy(itinerary, conflict)

            entry = ResolutionLogEntry(
                day_number=conflict.day_number,
                conflict_type=conflict.conflict_type,
                action=action,
                resolved=resolved,
            )
            log.append(entry)
            logger.info("Conflict resolution: %s", entry.model_dump())
            if not resolved:
                unresolved.append(conflict)

        return itinerary, log, unresolved

    @staticmethod
    def _day(itinerary: Itinerary, day_number: int) -> DayPlan:
        return next(d for d in itinerary.days if d.day_number == day_number)

    def _resolve_overlap(self, itinerary: Itinerary, conflict: Conflict) -> tuple[str, bool]:
        day = self._day(itinerary, conflict.day_number)
        items = sorted(day.items, key=lambda i: i.start_time)
        changed = False
        for a, b in zip(items, items[1:], strict=False):
            if a.end_time > b.start_time:
                delta = a.end_time - b.start_time
                b.start_time += delta
                b.end_time += delta
                changed = True
        if not changed:
            return "no overlap found to fix (already resolved)", True
        day.items = sorted(items, key=lambda i: i.start_time)
        return "shifted the later item to start after the earlier one ends", True

    def _resolve_impossible_travel(
        self, itinerary: Itinerary, conflict: Conflict
    ) -> tuple[str, bool]:
        day = self._day(itinerary, conflict.day_number)
        items = sorted(day.items, key=lambda i: i.start_time)
        changed = False
        for a, b in zip(items, items[1:], strict=False):
            if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
                continue
            gap = (b.start_time - a.end_time).total_seconds() / 60
            if gap < 0:
                continue
            required = self._travel_time.minutes_between(a.lat, a.lng, b.lat, b.lng)
            if gap < required:
                delta = timedelta(minutes=required - gap)
                b.start_time += delta
                b.end_time += delta
                changed = True
        if not changed:
            return "no impossible travel gap found to fix", True
        day.items = sorted(items, key=lambda i: i.start_time)
        return "pushed the later activity back to allow enough travel time", True

    def _resolve_max_activities(self, itinerary: Itinerary, conflict: Conflict) -> tuple[str, bool]:
        day = self._day(itinerary, conflict.day_number)
        removable = [i for i in day.items if i.activity_type in _ACTIVITY_TYPES]
        excess = len(removable) - self._max_activities_per_day
        if excess <= 0:
            return "activity count already within limit", True
        # drop the lowest-cost items first, as a simple stand-in for priority
        to_remove = sorted(removable, key=lambda i: i.cost or 0)[:excess]
        remove_ids = {id(i) for i in to_remove}
        day.items = [i for i in day.items if id(i) not in remove_ids]
        titles = ", ".join(i.title for i in to_remove)
        plural = "y" if excess == 1 else "ies"
        return f"removed {excess} lowest-priority activit{plural} ({titles})", True

    def _resolve_meal_time(self, itinerary: Itinerary, conflict: Conflict) -> tuple[str, bool]:
        day = self._day(itinerary, conflict.day_number)
        changed = False
        for item in day.items:
            if item.activity_type != "restaurant":
                continue
            t = item.start_time.time()
            in_lunch = LUNCH_WINDOW[0] <= t <= LUNCH_WINDOW[1]
            in_dinner = DINNER_WINDOW[0] <= t <= DINNER_WINDOW[1]
            if in_lunch or in_dinner:
                continue
            lunch_dt = datetime.combine(item.start_time.date(), _LUNCH_TARGET)
            dinner_dt = datetime.combine(item.start_time.date(), _DINNER_TARGET)
            target = min((lunch_dt, dinner_dt), key=lambda d: abs(d - item.start_time))
            duration = item.end_time - item.start_time
            item.start_time = target
            item.end_time = target + duration
            changed = True
        if not changed:
            return "no meal time violation found to fix", True
        day.items = sorted(day.items, key=lambda i: i.start_time)
        return "rescheduled the restaurant into the nearest valid meal window", True

    def _resolve_budget_overrun(self, itinerary: Itinerary, conflict: Conflict) -> tuple[str, bool]:
        prefs = itinerary.preferences
        candidates = [
            (day, item)
            for day in itinerary.days
            for item in day.items
            if item.activity_type in _ACTIVITY_TYPES and item.cost
        ]
        candidates.sort(key=lambda pair: pair[1].cost, reverse=True)  # priciest first

        total = estimate_itinerary_cost(itinerary)
        removed_titles: list[str] = []
        for day, item in candidates:
            if total <= prefs.budget_total:
                break
            day.items = [i for i in day.items if id(i) != id(item)]
            total -= item.cost
            removed_titles.append(item.title)

        if total <= prefs.budget_total:
            return (
                f"removed {len(removed_titles)} optional item(s) to fit budget: "
                f"{', '.join(removed_titles)}",
                True,
            )
        overage = total - prefs.budget_total
        return (
            f"removed all {len(removed_titles)} optional-cost item(s) but still "
            f"{overage:.2f} {prefs.budget_currency} over budget (fixed costs like "
            f"flights/hotel exceed it) — needs a decision",
            False,
        )


def detect_and_resolve(
    itinerary: Itinerary,
    detector: ConflictDetector,
    resolver: ConflictResolver,
    max_iterations: int = 5,
) -> tuple[Itinerary, list[ResolutionLogEntry], list[Conflict]]:
    """Detect, resolve, and re-detect: fixing one conflict can surface another
    (e.g. rescheduling a meal-time violation can create a new impossible-travel
    gap), so a single detect->resolve pass isn't always enough. Bounded by
    max_iterations rather than looping until convergence, since a genuinely
    unresolvable conflict (e.g. budget) would otherwise loop pointlessly.
    """
    all_log: list[ResolutionLogEntry] = []
    unresolved: list[Conflict] = []
    for _ in range(max_iterations):
        conflicts = detector.detect(itinerary)
        if not conflicts:
            unresolved = []
            break
        itinerary, log, unresolved = resolver.resolve(itinerary, conflicts)
        all_log.extend(log)
    return itinerary, all_log, unresolved
