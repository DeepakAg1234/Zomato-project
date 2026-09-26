"""Shared fixture store for retrieval tests — no Hugging Face, no network."""

from __future__ import annotations

import pandas as pd
import pytest

from src.ingest.clean import CANONICAL_COLUMNS, budget_band, restaurant_id
from src.store.restaurant_store import RestaurantStore


def restaurant_row(
    name: str,
    *,
    locality: str = "Indiranagar",
    city_zone: str = "Indiranagar",
    cuisines: list[str] | None = None,
    rest_types: list[str] | None = None,
    listing_type: str = "Dine-out",
    cost_for_two: int | None = 800,
    rating: float | None = 4.0,
    votes: int = 100,
    online_order: bool = True,
    book_table: bool = False,
    dishes_liked: list[str] | None = None,
) -> dict:
    address = f"{name} Road"
    return {
        "id": restaurant_id(name, address),
        "name": name,
        "locality": locality,
        "city_zone": city_zone,
        "address": address,
        "cuisines": cuisines if cuisines is not None else ["North Indian"],
        "rest_types": rest_types if rest_types is not None else ["Casual Dining"],
        "listing_type": listing_type,
        "cost_for_two": cost_for_two,
        "budget_band": budget_band(cost_for_two),
        "rating": rating,
        "votes": votes,
        "online_order": online_order,
        "book_table": book_table,
        "dishes_liked": dishes_liked if dishes_liked is not None else [],
        "review_excerpt": f"Nice food at {name}.",
        "url": f"https://example.test/{name.lower().replace(' ', '-')}",
    }


def build_store(rows: list[dict]) -> RestaurantStore:
    df = pd.DataFrame(rows)[CANONICAL_COLUMNS]
    df["cost_for_two"] = df["cost_for_two"].astype("Int64")
    df["rating"] = df["rating"].astype("Float64")
    df["votes"] = df["votes"].astype("int64")
    return RestaurantStore(df)


# 20 restaurants covering every filter, relaxation, and scoring case in
# docs/edge-case.md §"Phase 2". Indiranagar/medium/Italian is the happy path;
# the rest exist to be excluded or to be reached only through relaxation.
FIXTURE_ROWS = [
    # --- Indiranagar, medium budget, Italian: the core matching set ---
    restaurant_row("Trattoria Indira", cuisines=["Italian", "Pizza"], rating=4.5, votes=2000,
                   book_table=True),
    restaurant_row("Pasta Point", cuisines=["italian", "Continental"], rating=4.2, votes=900),
    restaurant_row("Olive Counter", cuisines=["Italian"], rating=4.0, votes=120),
    restaurant_row("Pizza Dash", cuisines=["Italian", "Fast Food"], rating=3.8, votes=4000,
                   rest_types=["Quick Bites"], listing_type="Delivery"),
    # --- Indiranagar, medium, other cuisines ---
    restaurant_row("Curry Leaf", cuisines=["North Indian", "Chinese"], rating=4.4, votes=1500,
                   rest_types=["Casual Dining", "Buffet"], book_table=True),
    restaurant_row("Wok This Way", cuisines=["Chinese"], rating=4.1, votes=300),
    restaurant_row("Filter Room", cuisines=["Cafe", "Desserts"], rating=4.3, votes=700,
                   rest_types=["Cafe"], listing_type="Cafes", dishes_liked=["Coffee", "Waffles"]),
    restaurant_row("Grab And Go", cuisines=["Fast Food"], rating=3.9, votes=250,
                   rest_types=["Quick Bites"], listing_type="Delivery"),
    # --- Indiranagar, other budgets ---
    restaurant_row("Idli Corner", cuisines=["South Indian"], cost_for_two=200, rating=4.2,
                   votes=800, rest_types=["Quick Bites"]),
    restaurant_row("Cheap Pasta", cuisines=["Italian"], cost_for_two=350, rating=3.6, votes=90),
    restaurant_row("Fine Italia", cuisines=["Italian"], cost_for_two=2500, rating=4.6, votes=1800,
                   rest_types=["Fine Dining"], book_table=True),
    restaurant_row("Cost Unknown Cafe", cuisines=["Italian"], cost_for_two=None, rating=4.1,
                   votes=400, rest_types=["Cafe"]),
    # --- Unrated and edge ratings in Indiranagar ---
    restaurant_row("Brand New Bistro", cuisines=["Italian"], rating=None, votes=0),
    restaurant_row("Exactly Four", cuisines=["Italian"], rating=4.0, votes=10),
    restaurant_row("Just Under", cuisines=["Italian"], rating=3.9, votes=10),
    restaurant_row("No Cuisine Listed", cuisines=[], rating=4.3, votes=600),
    # --- Same city zone, different locality: reachable only by relaxation ---
    restaurant_row("Zone Italian", locality="Old Airport Road", city_zone="Indiranagar",
                   cuisines=["Italian"], rating=4.4, votes=1100),
    restaurant_row("Zone Bistro", locality="Old Airport Road", city_zone="Indiranagar",
                   cuisines=["Continental"], rating=4.2, votes=500),
    # --- Different zone entirely: never matches an Indiranagar search ---
    restaurant_row("Kora Italian", locality="Koramangala 5th Block", city_zone="Koramangala",
                   cuisines=["Italian"], rating=4.7, votes=5000),
    restaurant_row("BTM Bites", locality="BTM", city_zone="BTM", cuisines=["Chinese"],
                   rating=4.0, votes=200),
]


@pytest.fixture
def store() -> RestaurantStore:
    return build_store(FIXTURE_ROWS)


def names(candidates) -> list[str]:
    return [c.restaurant.name for c in candidates]
