"""RouteOptimizerTool — Week 10 deliverable.

Orders a day's activities to minimize total travel time: Nearest Neighbor
construction (a classic greedy TSP approximation) followed by 2-opt local search.
The hotel (matrix index 0, by convention) is a fixed start AND end point — "start
near hotel, end near hotel" — matching how a real day actually runs.

Distances are used exactly as given and never assumed symmetric. Google's real
driving/transit data already reflects one-way streets and transit-line
asymmetries (A->B and B->A legitimately differ), which matters for correctness
here: naive 2-opt only re-checks the two boundary edges of a reversed segment,
which is only valid when internal edges cost the same in both directions. On an
asymmetric matrix, reversing a segment also flips the direction of every edge
*inside* it, so this implementation recomputes the full tour length for each
candidate swap rather than taking the boundary-only shortcut — more work
per check, but correct, and daily activity counts are small enough (a handful to
a couple dozen stops) that it's still fast.
"""

from __future__ import annotations

import random

Matrix = list[list[float]]


def tour_length(matrix: Matrix, tour: list[int]) -> float:
    return sum(matrix[tour[k]][tour[k + 1]] for k in range(len(tour) - 1))


def random_tour(n: int, start_index: int = 0, rng: random.Random | None = None) -> list[int]:
    """A closed-loop tour visiting every index 0..n-1 in a random order, used as
    the naive baseline for route_efficiency_score."""
    rng = rng or random.Random()
    others = [i for i in range(n) if i != start_index]
    rng.shuffle(others)
    return [start_index, *others, start_index] if others else [start_index]


def route_efficiency_score(
    matrix: Matrix, optimized_tour: list[int], naive_tour: list[int]
) -> float:
    """naive_length / optimized_length — 1.0 means no improvement possible,
    higher means the optimized route is proportionally faster than naive."""
    optimized_length = tour_length(matrix, optimized_tour)
    naive_length = tour_length(matrix, naive_tour)
    if optimized_length <= 0:
        return 1.0
    return naive_length / optimized_length


class RouteOptimizerTool:
    def optimize(
        self, matrix: Matrix, start_index: int = 0, max_2opt_passes: int = 100
    ) -> list[int]:
        """Returns a closed-loop tour (starts and ends at start_index) visiting
        every other index exactly once, approximately minimizing total travel
        time. `matrix[i][j]` is the cost from i to j; not assumed == matrix[j][i].
        """
        n = len(matrix)
        if n <= 1:
            return [start_index] if n == 1 else []
        tour = self.nearest_neighbor_tour(matrix, start_index)
        return self._two_opt(matrix, tour, max_2opt_passes)

    @staticmethod
    def nearest_neighbor_tour(matrix: Matrix, start_index: int = 0) -> list[int]:
        n = len(matrix)
        if n <= 1:
            return [start_index] if n == 1 else []
        visited = {start_index}
        tour = [start_index]
        current = start_index
        while len(visited) < n:
            nxt = min((j for j in range(n) if j not in visited), key=lambda j: matrix[current][j])
            tour.append(nxt)
            visited.add(nxt)
            current = nxt
        tour.append(start_index)
        return tour

    def _two_opt(self, matrix: Matrix, tour: list[int], max_passes: int) -> list[int]:
        best = tour
        best_length = tour_length(matrix, best)
        for _ in range(max_passes):
            improved = False
            for i in range(1, len(best) - 2):
                for j in range(i + 1, len(best) - 1):
                    candidate = best[:i] + best[i : j + 1][::-1] + best[j + 1 :]
                    candidate_length = tour_length(matrix, candidate)
                    if candidate_length < best_length - 1e-9:
                        best, best_length = candidate, candidate_length
                        improved = True
            if not improved:
                break
        return best
