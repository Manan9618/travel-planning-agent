import random

from travel_agent.tools.route_optimizer import (
    RouteOptimizerTool,
    random_tour,
    route_efficiency_score,
    tour_length,
)

LINE_MATRIX = [
    [0, 1, 2, 3, 4],
    [1, 0, 1, 2, 3],
    [2, 1, 0, 1, 2],
    [3, 2, 1, 0, 1],
    [4, 3, 2, 1, 0],
]

# forward (0->1->2->3->0) is cheap, backward is expensive — a one-way-street analog
ONE_WAY_MATRIX = [
    [0, 1, 100, 100],
    [100, 0, 1, 100],
    [100, 100, 0, 1],
    [1, 100, 100, 0],
]


def _optimizer():
    return RouteOptimizerTool()


# --- edge cases ---------------------------------------------------


def test_empty_matrix_returns_empty_tour():
    assert _optimizer().optimize([]) == []


def test_single_point_returns_just_the_start():
    assert _optimizer().optimize([[0]]) == [0]


def test_two_points_visits_both_and_returns():
    matrix = [[0, 5], [5, 0]]
    tour = _optimizer().optimize(matrix)
    assert tour == [0, 1, 0]


# --- nearest neighbor construction ---------------------------------------------------


def test_nearest_neighbor_visits_every_point_exactly_once():
    tour = RouteOptimizerTool.nearest_neighbor_tour(LINE_MATRIX)
    assert tour[0] == tour[-1] == 0
    assert sorted(tour[:-1]) == [0, 1, 2, 3, 4]


def test_nearest_neighbor_greedily_picks_closest_next_hop():
    # from hotel (0), the greedy nearest neighbor is 1 (cost 1), not 2/3/4
    tour = RouteOptimizerTool.nearest_neighbor_tour(LINE_MATRIX)
    assert tour[1] == 1


def test_nearest_neighbor_empty_and_single():
    assert RouteOptimizerTool.nearest_neighbor_tour([]) == []
    assert RouteOptimizerTool.nearest_neighbor_tour([[0]]) == [0]


# --- 2-opt improvement + optimize() ---------------------------------------------------


def test_optimize_finds_true_optimum_on_line_scenario():
    tour = _optimizer().optimize(LINE_MATRIX)
    assert tour_length(LINE_MATRIX, tour) == 8  # straight there-and-back is optimal


def test_optimize_never_produces_a_longer_tour_than_nearest_neighbor_alone():
    rng = random.Random(1)
    for _ in range(20):
        n = rng.randint(2, 8)
        matrix = [[0 if i == j else rng.randint(1, 50) for j in range(n)] for i in range(n)]
        nn_only = RouteOptimizerTool.nearest_neighbor_tour(matrix)
        optimized = _optimizer().optimize(matrix)
        assert tour_length(matrix, optimized) <= tour_length(matrix, nn_only) + 1e-9


def test_optimize_returns_a_valid_permutation_for_various_sizes():
    rng = random.Random(2)
    for n in range(2, 10):
        matrix = [[0 if i == j else rng.randint(1, 100) for j in range(n)] for i in range(n)]
        tour = _optimizer().optimize(matrix)
        assert tour[0] == tour[-1] == 0
        assert sorted(tour[:-1]) == list(range(n))


def test_max_2opt_passes_zero_skips_improvement_entirely():
    # a scenario where 2-opt WOULD improve on NN if allowed to run
    tour_with_no_2opt = _optimizer().optimize(ONE_WAY_MATRIX, max_2opt_passes=0)
    nn_only = RouteOptimizerTool.nearest_neighbor_tour(ONE_WAY_MATRIX)
    assert tour_with_no_2opt == nn_only


def test_two_opt_correctly_rejects_swap_that_looks_good_on_boundary_edges_alone():
    # Constructed so a *boundary-only* 2-opt check would wrongly accept swapping
    # positions 1,2 in [0,2,1,3,0] -> [0,1,2,3,0]: boundary edges look far cheaper
    # (0,1)+(2,3)=1+1=2 vs (0,2)+(1,3)=5+5=10 — but the internal edge that flips
    # direction on reversal, (2,1)=1 -> (1,2)=100, makes the full swap disastrous.
    matrix = [
        [0, 1, 5, 1000],
        [1000, 0, 100, 5],
        [5, 1, 0, 1000],
        [1000, 1000, 1, 0],
    ]
    tour = _optimizer()._two_opt(matrix, [0, 2, 1, 3, 0], max_passes=10)
    assert tour == [0, 2, 1, 3, 0]


def test_asymmetric_one_way_matrix_finds_the_cheap_loop_not_the_expensive_reverse():
    tour = _optimizer().optimize(ONE_WAY_MATRIX)
    assert tour == [0, 1, 2, 3, 0]
    assert tour_length(ONE_WAY_MATRIX, tour) == 4


# --- tour_length / random_tour / route_efficiency_score --------------------


def test_tour_length_sums_consecutive_edges():
    assert tour_length(LINE_MATRIX, [0, 1, 2, 0]) == 1 + 1 + 2


def test_random_tour_visits_every_point_once_and_returns_to_start():
    rng = random.Random(3)
    tour = random_tour(6, start_index=0, rng=rng)
    assert tour[0] == tour[-1] == 0
    assert sorted(tour[:-1]) == list(range(6))


def test_random_tour_is_deterministic_given_a_seeded_rng():
    tour_a = random_tour(6, rng=random.Random(42))
    tour_b = random_tour(6, rng=random.Random(42))
    assert tour_a == tour_b


def test_random_tour_single_point():
    assert random_tour(1) == [0]


def test_route_efficiency_score_greater_than_one_when_optimized_is_better():
    optimized = [0, 1, 2, 3, 4, 0]  # length 8, the true optimum
    naive = [0, 4, 1, 3, 2, 0]  # a bad zigzag, length 12
    score = route_efficiency_score(LINE_MATRIX, optimized, naive)
    assert score == 12 / 8


def test_route_efficiency_score_one_when_tours_are_identical():
    tour = [0, 1, 2, 3, 4, 0]
    assert route_efficiency_score(LINE_MATRIX, tour, tour) == 1.0


def test_route_efficiency_score_handles_zero_length_optimized_tour():
    assert route_efficiency_score([[0]], [0], [0]) == 1.0
