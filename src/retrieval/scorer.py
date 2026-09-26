"""Soft scoring that picks the K candidates the LLM will see (architecture §5.4).

    score = 0.45 * rating + 0.25 * log-votes + 0.20 * cuisine overlap
          + 0.10 * extra-preference heuristic

Extra preferences are keyword matching only. Free text can move a candidate up
or down this list; it can never change who is eligible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from src.models import Candidate, Restaurant, UserPreferences
from src.store.restaurant_store import RestaurantStore

DEFAULT_CANDIDATE_CAP = 12
MIN_CANDIDATE_CAP = 8
MAX_CANDIDATE_CAP = 15

WEIGHT_RATING = 0.45
WEIGHT_VOTES = 0.25
WEIGHT_CUISINE = 0.20
WEIGHT_EXTRA = 0.10

MAX_RATING = 5.0
HIGH_RATING = 4.2


@dataclass(frozen=True)
class _Row:
    """Lowercased view of one restaurant, built once per scoring pass."""

    rest_types: str
    listing_type: str
    dishes: str
    cuisines: str
    online_order: bool
    book_table: bool
    rating: float | None
    cost_for_two: int | None


@dataclass(frozen=True)
class _Heuristic:
    keywords: tuple[str, ...]
    signals: tuple[Callable[[_Row], bool], ...]


HEURISTICS: tuple[_Heuristic, ...] = (
    _Heuristic(
        keywords=("family", "kids", "children", "group", "parents"),
        signals=(
            lambda r: "casual dining" in r.rest_types or "family" in r.rest_types,
            lambda r: "buffet" in r.rest_types or "buffet" in r.listing_type,
            lambda r: r.book_table,
        ),
    ),
    _Heuristic(
        keywords=("quick", "fast", "takeaway", "take away", "grab", "in a hurry"),
        signals=(
            lambda r: "quick bites" in r.rest_types or "takeaway" in r.rest_types,
            lambda r: "delivery" in r.listing_type or "cafe" in r.rest_types,
            lambda r: r.online_order,
        ),
    ),
    _Heuristic(
        keywords=("date", "romantic", "anniversary", "candle"),
        signals=(
            lambda r: r.book_table,
            lambda r: "dessert" in r.cuisines or "fine dining" in r.rest_types,
            lambda r: r.rating is not None and r.rating >= HIGH_RATING,
        ),
    ),
    _Heuristic(
        keywords=("cafe", "café", "coffee", "outdoor", "rooftop", "work", "laptop"),
        signals=(
            lambda r: "cafe" in r.rest_types or "café" in r.rest_types,
            lambda r: "cafes" in r.listing_type or "coffee" in r.cuisines,
            lambda r: "coffee" in r.dishes or "cappuccino" in r.dishes,
        ),
    ),
)


def _row_view(restaurant: Restaurant) -> _Row:
    def joined(values: list[str]) -> str:
        return " | ".join(values).lower()

    return _Row(
        rest_types=joined(restaurant.rest_types),
        listing_type=restaurant.listing_type.lower(),
        dishes=joined(restaurant.dishes_liked),
        cuisines=joined(restaurant.cuisines),
        online_order=restaurant.online_order,
        book_table=restaurant.book_table,
        rating=restaurant.rating,
        cost_for_two=restaurant.cost_for_two,
    )


def active_heuristics(extra_preferences: str) -> tuple[_Heuristic, ...]:
    text = extra_preferences.lower()
    return tuple(h for h in HEURISTICS if any(k in text for k in h.keywords))


def extra_preference_score(row: _Row, heuristics: tuple[_Heuristic, ...]) -> float:
    """Mean share of matched signals across the triggered keyword groups."""
    if not heuristics:
        return 0.0
    per_group = [
        sum(1 for signal in h.signals if signal(row)) / len(h.signals) for h in heuristics
    ]
    return sum(per_group) / len(per_group)


def cuisine_overlap(restaurant_cuisines: list[str], requested: frozenset[str]) -> float:
    if not requested:
        return 0.0
    have = {c.lower() for c in restaurant_cuisines}
    return len(have & requested) / len(requested)


def score_rows(
    store: RestaurantStore,
    rows: np.ndarray,
    preferences: UserPreferences,
    *,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
) -> list[Candidate]:
    """Score `rows`, sort best first, and cap at K.

    Ties break on `id`, so identical preferences always produce an identical
    candidate list in an identical order.
    """
    if not MIN_CANDIDATE_CAP <= candidate_cap <= MAX_CANDIDATE_CAP:
        raise ValueError(
            f"candidate_cap must be between {MIN_CANDIDATE_CAP} and {MAX_CANDIDATE_CAP}"
        )
    if len(rows) == 0:
        return []

    requested_cuisines = frozenset(c.lower() for c in preferences.cuisines)
    heuristics = active_heuristics(preferences.extra_preferences)

    restaurants = [store.to_restaurant(int(row)) for row in rows]
    log_votes = [math.log1p(max(r.votes, 0)) for r in restaurants]
    max_log_votes = max(log_votes)

    candidates: list[Candidate] = []
    for restaurant, votes_component in zip(restaurants, log_votes):
        breakdown = {
            "rating": (restaurant.rating or 0.0) / MAX_RATING,
            "votes": votes_component / max_log_votes if max_log_votes > 0 else 0.0,
            "cuisine": cuisine_overlap(restaurant.cuisines, requested_cuisines),
            "extra": extra_preference_score(_row_view(restaurant), heuristics),
        }
        score = (
            WEIGHT_RATING * breakdown["rating"]
            + WEIGHT_VOTES * breakdown["votes"]
            + WEIGHT_CUISINE * breakdown["cuisine"]
            + WEIGHT_EXTRA * breakdown["extra"]
        )
        candidates.append(
            Candidate(
                restaurant=restaurant,
                score=round(score, 6),
                score_breakdown={k: round(v, 6) for k, v in breakdown.items()},
            )
        )

    candidates.sort(key=lambda c: (-c.score, c.restaurant.id))
    return candidates[:candidate_cap]
