"""MultiDayOptimizer — Week 11 deliverable: the unified multi-constraint optimizer.

`ItineraryBuilder` (Week 5/7) decides time slots and weather-swaps within a day,
but chooses WHICH attractions go on WHICH day with a naive rating-sorted
round-robin — no awareness of which attractions sit near each other (Week 9's
clustering), no route optimization of the visiting order (Week 10), no
guarantee that a user's "must-see" attractions actually get scheduled, and no
per-day budget awareness (Week 8) or cross-day walking-distance balance.

`MultiDayOptimizer` sits *above* `ItineraryBuilder`: it decides the day-by-day
attraction assignment using clustering + must-see priority + a bounded
backtracking search against a per-day activity-budget constraint, route-
optimizes each day's visiting order, and rebalances walking distance across
days — then delegates the actual time-slot/weather-swap mechanics for each day
to `ItineraryBuilder.build_day()`, reusing that tested Week 5/7 logic rather
than duplicating it.
"""

from __future__ import annotations

from itertools import combinations

from travel_agent.models.core import (
    Attraction,
    FlightOption,
    HotelOption,
    Itinerary,
    Restaurant,
    TravelPreferences,
    WeatherForecast,
)
from travel_agent.tools.budget_optimizer import BudgetOptimizer
from travel_agent.tools.distance_matrix import DistanceMatrixTool, TravelTimeEstimator
from travel_agent.tools.geo_clustering import cluster_attractions
from travel_agent.tools.itinerary_builder import ItineraryBuilder, trip_dates
from travel_agent.tools.route_optimizer import RouteOptimizerTool, tour_length

SLOTS_PER_DAY = 2

# Bounds the backtracking search's branching factor: only the top N highest-
# priority remaining attractions are considered as candidates for a day's
# slots. Keeps the search fast (well under the <5s/7-day target) regardless of
# how many attractions were found, at the cost of not exploring every
# combination — acceptable since candidates are already priority-sorted, so
# the combinations most worth trying are examined first anyway.
MAX_CANDIDATES_PER_DAY = 4
BUDGET_TOLERANCE = 1.25  # soft cap: allow a day to run up to 25% over its share

BALANCE_THRESHOLD_MINUTES = 20.0
MAX_BALANCE_SWAPS = 5


def _is_must_see(attraction: Attraction, must_see_terms: list[str]) -> bool:
    if not must_see_terms:
        return False
    name_lower = attraction.name.lower()
    return any(term.lower() in name_lower for term in must_see_terms)


def _priority_sorted(
    attractions: list[Attraction], labels: list[int], must_see_terms: list[str]
) -> list[Attraction]:
    """Must-see attractions first (highest-rated first among them), then
    everything else grouped by geographic cluster (largest cluster first, so
    cohesive groups of nearby attractions tend to land on the same day) and
    rating-sorted within each cluster.
    """
    must_see: list[Attraction] = []
    nice_to_have: list[tuple[Attraction, int]] = []
    for attraction, label in zip(attractions, labels, strict=True):
        if _is_must_see(attraction, must_see_terms):
            must_see.append(attraction)
        else:
            nice_to_have.append((attraction, label))

    must_see.sort(key=lambda a: -(a.rating or 0))

    by_cluster: dict[int, list[Attraction]] = {}
    for attraction, label in nice_to_have:
        by_cluster.setdefault(label, []).append(attraction)
    ordered_clusters = sorted(by_cluster.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    nice_sorted: list[Attraction] = []
    for _, members in ordered_clusters:
        members.sort(key=lambda a: -(a.rating or 0))
        nice_sorted.extend(members)

    return must_see + nice_sorted


class MultiDayOptimizer:
    def __init__(
        self,
        itinerary_builder: ItineraryBuilder | None = None,
        route_optimizer: RouteOptimizerTool | None = None,
        travel_time_estimator: TravelTimeEstimator | None = None,
        distance_matrix_tool: DistanceMatrixTool | None = None,
        budget_optimizer: BudgetOptimizer | None = None,
    ) -> None:
        self._travel_time = travel_time_estimator or TravelTimeEstimator()
        self._builder = itinerary_builder or ItineraryBuilder(self._travel_time)
        self._route_optimizer = route_optimizer or RouteOptimizerTool()
        self._distance_matrix_tool = distance_matrix_tool or DistanceMatrixTool()
        self._budget_optimizer = budget_optimizer or BudgetOptimizer()

    def build(
        self,
        preferences: TravelPreferences,
        hotel: HotelOption,
        attractions: list[Attraction],
        restaurants: list[Restaurant],
        flight: FlightOption | None = None,
        weather: list[WeatherForecast] | None = None,
        hotels: list[HotelOption] | None = None,
    ) -> Itinerary:
        # Multi-destination trips (preferences.additional_destinations) get
        # their own path entirely — see _build_multi_destination — so a
        # single-destination trip (the overwhelming common case) runs
        # through exactly the same code below as before this feature
        # existed, unchanged.
        destinations = [preferences.destination, *preferences.additional_destinations]
        if len(destinations) > 1:
            return self._build_multi_destination(
                preferences,
                destinations,
                hotel,
                hotels or [hotel],
                attractions,
                restaurants,
                flight,
                weather,
            )

        dates = trip_dates(preferences)
        num_days = len(dates)
        num_full_days = max(num_days - 2, 0)

        if num_full_days == 0 or not attractions:
            # Nothing to optimize (arrival-only trip, or no attractions found at
            # all) — fall back to the plain builder rather than run a search
            # over an empty problem.
            return self._builder.build(
                preferences, hotel, attractions, restaurants, flight, weather
            )

        weather_by_date = {w.day: w for w in (weather or [])}

        labels = cluster_attractions(attractions)
        priority = _priority_sorted(attractions, labels, preferences.must_see)
        per_day_budget = self._per_day_activity_budget(preferences, flight, num_full_days)

        # One batched Distance Matrix call covering the hotel + every attraction
        # that could possibly be scheduled (the priority pool, bounded to the
        # number of available slots) — every later travel-time lookup used for
        # day-cost estimation, cross-day balancing, and per-day route ordering
        # is a lookup into this matrix, not a fresh network call. This is what
        # keeps the optimizer itself fast regardless of how much balancing/
        # re-ordering search it does.
        total_slots = num_full_days * SLOTS_PER_DAY
        pool = priority[:total_slots]
        points = [(hotel.lat, hotel.lng)] + [(a.lat, a.lng) for a in pool]
        matrix = self._distance_matrix_tool.compute_matrix(points)
        index_of = {id(a): i + 1 for i, a in enumerate(pool)}

        day_assignments = self._assign_attractions_to_days(priority, num_full_days, per_day_budget)
        day_assignments = self._balance_days(day_assignments, matrix, index_of)
        day_assignments = [self._ordered_day(day, matrix, index_of) for day in day_assignments]

        days = []
        for day_index, current_date in enumerate(dates):
            day_number = day_index + 1
            forecast = weather_by_date.get(current_date)
            if day_index == 0:
                day_plan = self._builder.build_day(
                    day_number,
                    current_date,
                    "arrival",
                    hotel,
                    restaurants,
                    flight=flight,
                    destination=preferences.destination,
                    forecast=forecast,
                )
            elif day_index == num_days - 1:
                day_plan = self._builder.build_day(
                    day_number, current_date, "departure", hotel, restaurants, forecast=forecast
                )
            else:
                full_day_idx = day_index - 1
                day_plan = self._builder.build_day(
                    day_number,
                    current_date,
                    "full",
                    hotel,
                    restaurants,
                    attractions=day_assignments[full_day_idx],
                    forecast=forecast,
                )
            days.append(day_plan)

        return Itinerary(
            preferences=preferences, days=days, flights=[flight] if flight else [], hotel=hotel
        )

    # --- multi-destination trips ---------------------------------------------

    @staticmethod
    def _partition_full_days(num_full_days: int, num_destinations: int) -> list[int]:
        """Splits the trip's full days as evenly as possible across
        destinations, in visiting order — any remainder goes to the
        earlier destinations first (e.g. 5 full days over 3 cities ->
        [2, 2, 1]), rather than leaving a later city with nothing purely
        because the split doesn't divide evenly."""
        base, remainder = divmod(num_full_days, num_destinations)
        return [base + (1 if i < remainder else 0) for i in range(num_destinations)]

    def _build_multi_destination(
        self,
        preferences: TravelPreferences,
        destinations: list[str],
        primary_hotel: HotelOption,
        hotels: list[HotelOption],
        attractions: list[Attraction],
        restaurants: list[Restaurant],
        flight: FlightOption | None,
        weather: list[WeatherForecast] | None,
    ) -> Itinerary:
        """Runs the exact same clustering + priority + budget-aware
        backtracking + cross-day balancing + route-ordering pipeline as
        `build()`'s single-destination path — just once per destination,
        against that city's own attraction/restaurant pool and its own
        share of the trip's full days, then stitches the results together
        in visiting order. Deliberately does not model travel between
        cities (no separate flight/train leg, no transition day) — the
        lighter multi-destination scope this feature was built to.
        """
        dates = trip_dates(preferences)
        num_days = len(dates)
        num_full_days = max(num_days - 2, 0)
        weather_by_date = {w.day: w for w in (weather or [])}

        def hotel_for(dest: str) -> HotelOption:
            return next((h for h in hotels if h.destination == dest), primary_hotel)

        def attractions_for(dest: str) -> list[Attraction]:
            return [a for a in attractions if (a.destination or destinations[0]) == dest]

        def restaurants_for(dest: str) -> list[Restaurant]:
            return [r for r in restaurants if (r.destination or destinations[0]) == dest]

        # One shared per-day activity rate (computed once, from the whole
        # trip's budget) rather than recomputing it per destination block —
        # dividing the total activity budget by only *that* block's day
        # count would let every block think the full trip's activity
        # budget was available just to it, silently multiplying the
        # effective budget by the number of destinations.
        per_day_budget = self._per_day_activity_budget(preferences, flight, num_full_days)
        day_counts = self._partition_full_days(num_full_days, len(destinations))

        per_destination_days: list[list[Attraction]] = []
        for dest, count in zip(destinations, day_counts, strict=True):
            dest_attractions = attractions_for(dest)
            if count == 0 or not dest_attractions:
                per_destination_days.extend([[] for _ in range(count)])
                continue
            dest_hotel = hotel_for(dest)
            labels = cluster_attractions(dest_attractions)
            priority = _priority_sorted(dest_attractions, labels, preferences.must_see)

            total_slots = count * SLOTS_PER_DAY
            pool = priority[:total_slots]
            points = [(dest_hotel.lat, dest_hotel.lng)] + [(a.lat, a.lng) for a in pool]
            matrix = self._distance_matrix_tool.compute_matrix(points)
            index_of = {id(a): i + 1 for i, a in enumerate(pool)}

            day_assignments = self._assign_attractions_to_days(priority, count, per_day_budget)
            day_assignments = self._balance_days(day_assignments, matrix, index_of)
            day_assignments = [self._ordered_day(day, matrix, index_of) for day in day_assignments]
            per_destination_days.extend(day_assignments)

        full_day_destination: list[str] = []
        for dest, count in zip(destinations, day_counts, strict=True):
            full_day_destination.extend([dest] * count)

        days = []
        for day_index, current_date in enumerate(dates):
            day_number = day_index + 1
            forecast = weather_by_date.get(current_date)
            if day_index == 0:
                first_dest = destinations[0]
                day_plan = self._builder.build_day(
                    day_number,
                    current_date,
                    "arrival",
                    hotel_for(first_dest),
                    restaurants_for(first_dest),
                    flight=flight,
                    destination=first_dest,
                    forecast=forecast,
                )
            elif day_index == num_days - 1:
                last_dest = destinations[-1]
                day_plan = self._builder.build_day(
                    day_number,
                    current_date,
                    "departure",
                    hotel_for(last_dest),
                    restaurants_for(last_dest),
                    forecast=forecast,
                )
            else:
                full_day_idx = day_index - 1
                dest = (
                    full_day_destination[full_day_idx]
                    if full_day_idx < len(full_day_destination)
                    else destinations[-1]
                )
                day_attractions = (
                    per_destination_days[full_day_idx]
                    if full_day_idx < len(per_destination_days)
                    else []
                )
                day_plan = self._builder.build_day(
                    day_number,
                    current_date,
                    "full",
                    hotel_for(dest),
                    restaurants_for(dest),
                    attractions=day_attractions,
                    forecast=forecast,
                )
            days.append(day_plan)

        return Itinerary(
            preferences=preferences,
            days=days,
            flights=[flight] if flight else [],
            hotel=primary_hotel,
        )

    # --- day-assignment backtracking search ---------------------------------

    def _per_day_activity_budget(
        self, preferences: TravelPreferences, flight: FlightOption | None, num_full_days: int
    ) -> float | None:
        if not preferences.budget_total or num_full_days <= 0:
            return None
        allocation = self._budget_optimizer.allocate(
            preferences.budget_total,
            flight.price if flight else 0.0,
            tier=preferences.budget_tier,
            priority_weights=preferences.priority_weights,
        )
        return allocation.activities / num_full_days

    def _assign_attractions_to_days(
        self,
        priority_sorted: list[Attraction],
        num_days: int,
        per_day_budget: float | None,
    ) -> list[list[Attraction]]:
        """Recursive backtracking: fills each day's two slots from the
        priority-ordered pool. Candidate pairs are tried highest-priority-first;
        a pair that would push the day's estimated activity cost over its soft
        per-day budget is rejected and the search backtracks to try the next
        pair (or, having placed a day, backtracks into an earlier day if no
        combination works out for a later one). If every candidate for a day
        would exceed budget, falls back to the cheapest available pair so a day
        is never left empty just because nothing "fit" on paper.
        """
        total_slots = num_days * SLOTS_PER_DAY
        pool = priority_sorted[:total_slots]
        assignment: list[list[Attraction]] = [[] for _ in range(num_days)]

        def backtrack(day: int, remaining: list[Attraction]) -> bool:
            if day == num_days:
                return True
            if not remaining:
                return True

            candidates = remaining[:MAX_CANDIDATES_PER_DAY]
            slot_size = min(SLOTS_PER_DAY, len(remaining))
            for combo in combinations(candidates, min(slot_size, len(candidates))):
                cost = sum(a.price or 0.0 for a in combo)
                if per_day_budget is not None and cost > per_day_budget * BUDGET_TOLERANCE:
                    continue  # constraint violated — backtrack, try the next combo
                assignment[day] = list(combo)
                rest = [a for a in remaining if a not in combo]
                if backtrack(day + 1, rest):
                    return True
                assignment[day] = []  # undo and try the next candidate combo

            # No combination satisfied the budget constraint for this day —
            # graceful degradation: take the cheapest available slot_size
            # attractions instead of leaving the day empty.
            cheapest = sorted(remaining, key=lambda a: a.price or 0.0)[:slot_size]
            assignment[day] = cheapest
            rest = [a for a in remaining if a not in cheapest]
            backtrack(day + 1, rest)
            return True

        backtrack(0, pool)
        return assignment

    # --- route optimization + cross-day balancing ---------------------------
    # All travel-time lookups below index into the single batched matrix
    # computed once in `build()` (hotel at index 0, each pool attraction at
    # `index_of[id(attraction)]`) rather than making fresh network calls.

    def _submatrix(self, matrix: list[list[float]], indices: list[int]) -> list[list[float]]:
        return [[matrix[i][j] for j in indices] for i in indices]

    def _day_travel_minutes(
        self,
        day_attractions: list[Attraction],
        matrix: list[list[float]],
        index_of: dict[int, int],
    ) -> float:
        if not day_attractions:
            return 0.0
        indices = [0] + [index_of[id(a)] for a in day_attractions]
        sub = self._submatrix(matrix, indices)
        tour = self._route_optimizer.optimize(sub)
        return tour_length(sub, tour)

    def _ordered_day(
        self,
        day_attractions: list[Attraction],
        matrix: list[list[float]],
        index_of: dict[int, int],
    ) -> list[Attraction]:
        if len(day_attractions) <= 1:
            return day_attractions
        indices = [0] + [index_of[id(a)] for a in day_attractions]
        sub = self._submatrix(matrix, indices)
        tour = self._route_optimizer.optimize(sub)
        order = [
            i - 1 for i in tour[1:-1]
        ]  # drop the hotel anchor, rebase to day_attractions indices
        return [day_attractions[i] for i in order]

    def _balance_days(
        self,
        day_assignments: list[list[Attraction]],
        matrix: list[list[float]],
        index_of: dict[int, int],
    ) -> list[list[Attraction]]:
        """Swaps one attraction between the most- and least-walking-heavy days,
        repeatedly, as long as an improving swap exists — distributing total
        travel distance more evenly across the trip rather than letting one day
        end up far more walking-intensive than the rest.
        """
        assignments = [list(day) for day in day_assignments]
        for _ in range(MAX_BALANCE_SWAPS):
            costs = [self._day_travel_minutes(day, matrix, index_of) for day in assignments]
            non_empty = [i for i, day in enumerate(assignments) if day]
            if len(non_empty) < 2:
                break
            worst = max(non_empty, key=lambda i: costs[i])
            best = min(non_empty, key=lambda i: costs[i])
            if worst == best or costs[worst] - costs[best] < BALANCE_THRESHOLD_MINUTES:
                break
            if not self._try_swap(assignments, worst, best, matrix, index_of):
                break
        return assignments

    def _try_swap(
        self,
        assignments: list[list[Attraction]],
        worst: int,
        best: int,
        matrix: list[list[float]],
        index_of: dict[int, int],
    ) -> bool:
        spread_before = abs(
            self._day_travel_minutes(assignments[worst], matrix, index_of)
            - self._day_travel_minutes(assignments[best], matrix, index_of)
        )
        best_swap: tuple[float, int, int] | None = None
        for i in range(len(assignments[worst])):
            for j in range(len(assignments[best])):
                trial_worst = list(assignments[worst])
                trial_best = list(assignments[best])
                trial_worst[i], trial_best[j] = trial_best[j], trial_worst[i]
                new_spread = abs(
                    self._day_travel_minutes(trial_worst, matrix, index_of)
                    - self._day_travel_minutes(trial_best, matrix, index_of)
                )
                if new_spread < spread_before and (best_swap is None or new_spread < best_swap[0]):
                    best_swap = (new_spread, i, j)

        if best_swap is None:
            return False
        _, i, j = best_swap
        assignments[worst][i], assignments[best][j] = assignments[best][j], assignments[worst][i]
        return True
