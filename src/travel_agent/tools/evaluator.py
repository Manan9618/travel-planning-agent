"""ItineraryEvaluator — Week 12 deliverable: the code-computed half of the
evaluation framework (see `itinerary_judge.py` for the LLM-as-judge half).

The plan's rubric names 5 example dimensions (feasibility, budget accuracy,
geo-efficiency, weather-match, completeness); this adds a 6th (variety) and
computes all 6 directly from the itinerary and its own already-built tools —
ConflictDetector (Week 6), budget_adherence_score (Week 8),
weather_adaptation_rate (Week 7), and a route_efficiency_score-style ratio
(Week 10) — rather than asking an LLM to re-derive facts the code already
knows exactly. The remaining 4 (personalization_fit, narrative_quality,
practicality, overall_satisfaction) genuinely need judgment and come from
`ItineraryJudge`.
"""

from __future__ import annotations

import random

from travel_agent.models.core import DimensionScore, EvaluationReport, Itinerary
from travel_agent.tools.budget_tracker import budget_adherence_score
from travel_agent.tools.conflict_detector import ConflictDetector
from travel_agent.tools.distance_matrix import DistanceMatrixTool
from travel_agent.tools.itinerary_judge import ItineraryJudge
from travel_agent.tools.route_optimizer import random_tour, tour_length
from travel_agent.tools.weather_matcher import weather_adaptation_rate

CONFLICT_PENALTY_PER_ISSUE = 2.0
NAIVE_BASELINE_SAMPLES = 5
NAIVE_BASELINE_SEED = 42
GEO_EFFICIENCY_SCALE = 5.0  # ratio 1.0 (no improvement over naive) -> score 5.0


def _full_days(itinerary: Itinerary) -> list:
    return itinerary.days[1:-1] if len(itinerary.days) > 2 else []


class ItineraryEvaluator:
    def __init__(
        self,
        judge: ItineraryJudge | None = None,
        conflict_detector: ConflictDetector | None = None,
        distance_matrix_tool: DistanceMatrixTool | None = None,
    ) -> None:
        self._judge = judge or ItineraryJudge()
        self._conflict_detector = conflict_detector or ConflictDetector()
        self._distance_matrix_tool = distance_matrix_tool or DistanceMatrixTool()

    def evaluate(self, itinerary: Itinerary, scenario_label: str = "") -> EvaluationReport:
        dimensions = [
            self._feasibility(itinerary),
            self._budget_accuracy(itinerary),
            self._geo_efficiency(itinerary),
            self._weather_match(itinerary),
            self._completeness(itinerary),
            self._variety(itinerary),
            *self._llm_judged(itinerary),
        ]
        scored = [d.score for d in dimensions if d.score is not None]
        overall = sum(scored) / len(scored) if scored else 0.0
        return EvaluationReport(
            scenario_label=scenario_label, dimensions=dimensions, overall_score=overall
        )

    # --- computed dimensions -------------------------------------------------

    def _feasibility(self, itinerary: Itinerary) -> DimensionScore:
        conflicts = self._conflict_detector.detect(itinerary)
        score = max(0.0, 10.0 - CONFLICT_PENALTY_PER_ISSUE * len(conflicts))
        explanation = (
            "no conflicts detected"
            if not conflicts
            else f"{len(conflicts)} conflict(s) detected: "
            + "; ".join(c.conflict_type for c in conflicts[:3])
        )
        return DimensionScore(
            name="feasibility", score=score, method="computed", explanation=explanation
        )

    def _budget_accuracy(self, itinerary: Itinerary) -> DimensionScore:
        adherence = budget_adherence_score(itinerary)
        score = adherence * 10 if adherence is not None else None
        explanation = (
            "no budget stated" if adherence is None else f"{adherence:.0%} adherence to budget"
        )
        return DimensionScore(
            name="budget_accuracy", score=score, method="computed", explanation=explanation
        )

    def _weather_match(self, itinerary: Itinerary) -> DimensionScore:
        rate = weather_adaptation_rate(itinerary)
        score = rate * 10 if rate is not None else None
        explanation = (
            "no weather data available for any scheduled day"
            if rate is None
            else f"{rate:.0%} of attractions matched to conditions"
        )
        return DimensionScore(
            name="weather_match", score=score, method="computed", explanation=explanation
        )

    def _completeness(self, itinerary: Itinerary) -> DimensionScore:
        full_days = _full_days(itinerary)
        if full_days:
            filled = sum(
                1
                for d in full_days
                if sum(1 for i in d.items if i.activity_type == "attraction") >= 2
            )
            slot_fill_rate = filled / len(full_days)
        else:
            filled, slot_fill_rate = 0, 1.0  # nothing to fill -> vacuously complete

        must_see = itinerary.preferences.must_see
        if must_see:
            titles = [i.title.lower() for d in itinerary.days for i in d.items]
            hits = sum(1 for term in must_see if any(term.lower() in t for t in titles))
            must_see_rate = hits / len(must_see)
            score = 10 * (0.5 * slot_fill_rate + 0.5 * must_see_rate)
            explanation = (
                f"{filled}/{len(full_days)} full days fully scheduled, "
                f"{hits}/{len(must_see)} must-see attractions included"
            )
        else:
            score = 10 * slot_fill_rate
            explanation = (
                f"{filled}/{len(full_days)} full days fully scheduled"
                if full_days
                else "no full days in this trip"
            )
        return DimensionScore(
            name="completeness", score=score, method="computed", explanation=explanation
        )

    def _variety(self, itinerary: Itinerary) -> DimensionScore:
        attraction_items = [
            i for d in itinerary.days for i in d.items if i.activity_type == "attraction"
        ]
        if not attraction_items:
            return DimensionScore(
                name="variety",
                score=None,
                method="computed",
                explanation="no attractions scheduled",
            )
        categories = [i.category or "unknown" for i in attraction_items]
        distinct_ratio = len(set(categories)) / len(categories)
        score = 10 * distinct_ratio
        explanation = (
            f"{len(set(categories))} distinct categories across {len(categories)} attractions"
        )
        return DimensionScore(
            name="variety", score=score, method="computed", explanation=explanation
        )

    def _geo_efficiency(self, itinerary: Itinerary) -> DimensionScore:
        full_days = _full_days(itinerary)
        rng = random.Random(NAIVE_BASELINE_SEED)
        ratios = []
        for day in full_days:
            coords = [
                (i.lat, i.lng)
                for i in day.items
                if i.activity_type == "attraction" and i.lat is not None
            ]
            if len(coords) < 2 or not itinerary.hotel:
                continue
            points = [(itinerary.hotel.lat, itinerary.hotel.lng), *coords]
            matrix = self._distance_matrix_tool.compute_matrix(points)
            as_scheduled_tour = [*range(len(points)), 0]
            as_scheduled_length = tour_length(matrix, as_scheduled_tour)
            if as_scheduled_length <= 0:
                continue
            naive_lengths = [
                tour_length(matrix, random_tour(len(points), rng=rng))
                for _ in range(NAIVE_BASELINE_SAMPLES)
            ]
            avg_naive = sum(naive_lengths) / len(naive_lengths)
            ratios.append(avg_naive / as_scheduled_length)

        if not ratios:
            return DimensionScore(
                name="geo_efficiency",
                score=None,
                method="computed",
                explanation="not enough scheduled attractions to measure",
            )
        avg_ratio = sum(ratios) / len(ratios)
        score = min(10.0, GEO_EFFICIENCY_SCALE * avg_ratio)
        explanation = (
            f"{avg_ratio:.2f}x more efficient than naive random ordering, "
            f"averaged across {len(ratios)} day(s)"
        )
        return DimensionScore(
            name="geo_efficiency", score=score, method="computed", explanation=explanation
        )

    # --- LLM-judged dimensions -------------------------------------------------

    def _llm_judged(self, itinerary: Itinerary) -> list[DimensionScore]:
        judged = self._judge.judge(itinerary.preferences, itinerary)
        return [
            DimensionScore(
                name="personalization_fit",
                score=float(judged.personalization_fit),
                method="llm_judge",
                explanation=judged.explanation,
            ),
            DimensionScore(
                name="narrative_quality",
                score=float(judged.narrative_quality),
                method="llm_judge",
                explanation=judged.explanation,
            ),
            DimensionScore(
                name="practicality",
                score=float(judged.practicality),
                method="llm_judge",
                explanation=judged.explanation,
            ),
            DimensionScore(
                name="overall_satisfaction",
                score=float(judged.overall_satisfaction),
                method="llm_judge",
                explanation=judged.explanation,
            ),
        ]
