"""Presentation helpers kept independent from Streamlit for easy testing."""

from __future__ import annotations

from dataclasses import dataclass

from src.models import RecommendationItem


@dataclass(frozen=True)
class RestaurantCard:
    """Display-safe fields for one ranked recommendation card."""

    rank: int
    name: str
    cuisines: str
    rating: str
    cost: str
    locality: str
    explanation: str
    badges: tuple[str, ...]


def to_restaurant_card(item: RecommendationItem) -> RestaurantCard:
    """Map a service result to UI text without exposing private/raw fields."""
    badges: list[str] = []
    if item.book_table:
        badges.append("Table booking")
    if item.online_order:
        badges.append("Online ordering")

    return RestaurantCard(
        rank=item.rank,
        name=item.name,
        cuisines=", ".join(item.cuisines) if item.cuisines else "Cuisine not listed",
        rating=f"{item.rating:.1f} ★" if item.rating is not None else "Not rated",
        cost=(
            f"≈ ₹{item.cost_for_two:,} for two"
            if item.cost_for_two is not None
            else "Cost not listed"
        ),
        locality=item.locality,
        explanation=item.explanation,
        badges=tuple(badges),
    )
