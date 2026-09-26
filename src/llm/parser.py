"""Parse, ground, and join model output to canonical restaurant records."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.models import Candidate, RecommendationItem, Restaurant

MAX_EXPLANATION_CHARS = 400


class LLMParseError(ValueError):
    """The model response cannot produce any grounded recommendation."""


@dataclass(frozen=True)
class ParsedRecommendations:
    summary: str | None
    results: list[RecommendationItem]


def fallback_explanation(restaurant: Restaurant) -> str:
    rating = f"rated {restaurant.rating:.1f}/5" if restaurant.rating is not None else "currently unrated"
    cuisines = ", ".join(restaurant.cuisines[:3]) or "a varied menu"
    cost = (
        f"about ₹{restaurant.cost_for_two:,} for two"
        if restaurant.cost_for_two is not None
        else "no listed cost estimate"
    )
    return f"It offers {cuisines}, is {rating}, and has {cost}."


def recommendation_item(
    restaurant: Restaurant,
    *,
    rank: int,
    explanation: str | None = None,
) -> RecommendationItem:
    clean_explanation = (explanation or "").strip()
    if not clean_explanation:
        clean_explanation = fallback_explanation(restaurant)
    return RecommendationItem(
        id=restaurant.id,
        rank=rank,
        name=restaurant.name,
        cuisines=restaurant.cuisines,
        rating=restaurant.rating,
        votes=restaurant.votes,
        cost_for_two=restaurant.cost_for_two,
        locality=restaurant.locality,
        online_order=restaurant.online_order,
        book_table=restaurant.book_table,
        explanation=clean_explanation[:MAX_EXPLANATION_CHARS],
        url=restaurant.url,
    )


def fallback_results(
    candidates: list[Candidate],
    max_results: int,
) -> list[RecommendationItem]:
    return [
        recommendation_item(candidate.restaurant, rank=index)
        for index, candidate in enumerate(candidates[:max_results], start=1)
    ]


def _decode_object(raw: str) -> dict[str, object]:
    if not isinstance(raw, str) or not raw.strip():
        raise LLMParseError("LLM response is empty")
    start = raw.find("{")
    if start < 0:
        raise LLMParseError("LLM response does not contain a JSON object")
    try:
        value, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise LLMParseError("LLM response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise LLMParseError("LLM response root must be an object")
    return value


def parse_recommendations(
    raw: str,
    candidates: list[Candidate],
    max_results: int,
) -> ParsedRecommendations:
    """Keep only candidate ids, normalize ranks, and backfill short output."""
    payload = _decode_object(raw)
    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        raise LLMParseError("recommendations must be an array")

    candidate_by_id = {candidate.restaurant.id: candidate for candidate in candidates}
    sortable: list[tuple[int, int, str, str | None]] = []
    for position, value in enumerate(recommendations):
        if not isinstance(value, dict):
            continue
        restaurant_id = value.get("id")
        if not isinstance(restaurant_id, str) or restaurant_id not in candidate_by_id:
            continue
        raw_rank = value.get("rank")
        rank = raw_rank if isinstance(raw_rank, int) and not isinstance(raw_rank, bool) and raw_rank > 0 else position + 1
        explanation = value.get("explanation")
        sortable.append(
            (rank, position, restaurant_id, explanation if isinstance(explanation, str) else None)
        )

    sortable.sort(key=lambda item: (item[0], item[1]))
    selected: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for _, _, restaurant_id, explanation in sortable:
        if restaurant_id in seen:
            continue
        seen.add(restaurant_id)
        selected.append((restaurant_id, explanation))
        if len(selected) == max_results:
            break

    if not selected:
        raise LLMParseError("LLM response contains no known candidate ids")

    # Backfill from deterministic retrieval order when the model returns too few.
    for candidate in candidates:
        restaurant_id = candidate.restaurant.id
        if len(selected) == min(max_results, len(candidates)):
            break
        if restaurant_id not in seen:
            seen.add(restaurant_id)
            selected.append((restaurant_id, None))

    results = [
        recommendation_item(
            candidate_by_id[restaurant_id].restaurant,
            rank=rank,
            explanation=explanation,
        )
        for rank, (restaurant_id, explanation) in enumerate(selected, start=1)
    ]
    summary = payload.get("summary")
    return ParsedRecommendations(
        summary=summary.strip() if isinstance(summary, str) and summary.strip() else None,
        results=results,
    )


parse_llm_response = parse_recommendations
