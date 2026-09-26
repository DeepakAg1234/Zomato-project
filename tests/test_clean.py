import math

import pandas as pd
import pytest

from src.ingest.clean import (
    CANONICAL_COLUMNS,
    budget_band,
    build_facets,
    clean_dataframe,
    parse_bool,
    parse_cost,
    parse_rating,
    restaurant_id,
    review_excerpt,
    split_list,
)
from src.ingest.load_hf import write_outputs
from src.store.restaurant_store import RestaurantStore, StoreNotReadyError


def _row(name, address, *, location="Indiranagar", city="Indiranagar", rate="4.1/5",
         cost="800", votes=100, cuisines="North Indian, Chinese", rest_type="Casual Dining",
         online="Yes", book="No", dish_liked=None, reviews="[]", phone="080 1234567"):
    return {
        "url": f"https://www.zomato.com/{name.lower().replace(' ', '-')}",
        "address": address,
        "name": name,
        "online_order": online,
        "book_table": book,
        "rate": rate,
        "votes": votes,
        "phone": phone,
        "location": location,
        "rest_type": rest_type,
        "dish_liked": dish_liked,
        "cuisines": cuisines,
        "approx_cost(for two people)": cost,
        "reviews_list": reviews,
        "menu_item": "[]",
        "listed_in(type)": "Delivery",
        "listed_in(city)": city,
    }


@pytest.fixture
def raw_df() -> pd.DataFrame:
    long_review = "[('Rated 4.0', 'RATED\\n  " + "Great food and lovely ambience. " * 50 + "')]"
    rows = [
        _row("Toit", "298 100 Feet Rd", rate="4.7/5", cost="1,500", votes=14000,
             cuisines="Italian, American, Pizza", rest_type="Microbrewery", book="Yes",
             dish_liked="Pizza, Beer, Nachos", reviews=long_review),
        _row("Toit", "298 100 Feet Rd", rate="4.6/5", cost="1,500", votes=9000,
             city="Old Airport Road"),
        _row("Toit", "Another address, Koramangala", location="Koramangala 5th Block",
             city="Koramangala", votes=50),
        _row("Fresh Place", "1 Main St", rate="NEW", votes=0),
        _row("Dash Diner", "2 Main St", rate="-"),
        _row("Blank Rate", "3 Main St", rate=None),
        _row("Spaced Rating", "4 Main St", rate="3.9 /5"),
        _row("Spaced Slash", "5 Main St", rate="4.1 / 5"),
        _row("Bare Rating", "6 Main St", rate="4.1"),
        _row("Garbage Rating", "7 Main St", rate="Opening"),
        _row("Budget Low", "8 Main St", cost="400", cuisines="  Italian,  Chinese, "),
        _row("Budget Medium", "9 Main St", cost="401", cuisines="italian"),
        _row("Budget Edge", "10 Main St", cost="1000"),
        _row("Budget High", "11 Main St", cost="1001"),
        _row("No Cost", "12 Main St", cost=None),
        _row("Text Cost", "13 Main St", cost="not available"),
        _row("Café Unicode", "14 Main St", cuisines=None, rest_type=None,
             online="YES", book="yes"),
        _row("", "15 Main St"),
        _row("Equal Votes", "16 Main St", votes=10, rate="3.5/5"),
        _row("Equal Votes", "16 Main St", votes=10, rate="4.0/5"),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def cleaned(raw_df):
    df, stats = clean_dataframe(raw_df)
    return df.set_index("name", drop=False), stats


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("4.1/5", 4.1),
        ("3.9 /5", 3.9),
        ("4.1 / 5", 4.1),
        ("4.1", 4.1),
        ("5/5", 5.0),
        ("0", 0.0),
        ("NEW", None),
        ("-", None),
        ("", None),
        (None, None),
        (float("nan"), None),
        ("Opening", None),
        ("6.2/5", None),
    ],
)
def test_parse_rating(raw, expected):
    assert parse_rating(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("800", 800),
        ("1,200", 1200),
        ("1,200.00", 1200),
        ("₹1,200", 1200),
        ("0", None),
        ("", None),
        (None, None),
        (float("nan"), None),
        ("not available", None),
    ],
)
def test_parse_cost(raw, expected):
    assert parse_cost(raw) == expected


@pytest.mark.parametrize(
    "cost, band",
    [(None, "unknown"), (1, "low"), (400, "low"), (401, "medium"), (1000, "medium"),
     (1001, "high")],
)
def test_budget_band_boundaries(cost, band):
    assert budget_band(cost) == band


def test_split_list_trims_and_drops_empty():
    assert split_list("Italian, Chinese") == ["Italian", "Chinese"]
    assert split_list("  Italian,  Chinese, ") == ["Italian", "Chinese"]
    assert split_list(None) == []
    assert split_list("") == []


def test_parse_bool():
    assert parse_bool("Yes") and parse_bool("YES") and parse_bool("yes")
    assert not parse_bool("No") and not parse_bool("-") and not parse_bool(None)


def test_review_excerpt_is_bounded():
    assert review_excerpt("[]") is None
    assert review_excerpt(None) is None
    excerpt = review_excerpt("[('Rated 4.0', 'RATED\\n  " + "x" * 5000 + "')]")
    assert excerpt is not None and len(excerpt) <= 400
    assert "RATED" not in excerpt


def test_restaurant_id_is_stable_and_normalized():
    assert restaurant_id("Toit", "298 100 Feet Rd") == restaurant_id(" toit ", "298 100 FEET RD")
    assert restaurant_id("Toit", "a") != restaurant_id("Toit", "b")
    assert restaurant_id("No Address", "") == restaurant_id("No Address", "")


def test_clean_dataframe_schema_and_counts(raw_df, cleaned):
    df, stats = cleaned
    assert list(df.columns) == CANONICAL_COLUMNS
    assert stats.raw_rows == len(raw_df) == 20
    assert stats.cleaned_rows == 19
    assert stats.deduped_rows == 17
    assert "phone" not in df.columns
    assert "menu_item" not in df.columns
    assert df["id"].is_unique


def test_clean_dataframe_values(cleaned):
    df, _ = cleaned
    assert df.loc["Fresh Place", "rating"] is pd.NA
    assert df.loc["Dash Diner", "rating"] is pd.NA
    assert df.loc["Blank Rate", "rating"] is pd.NA
    assert df.loc["Garbage Rating", "rating"] is pd.NA
    assert math.isclose(df.loc["Spaced Rating", "rating"], 3.9)
    assert math.isclose(df.loc["Bare Rating", "rating"], 4.1)

    assert df.loc["Budget Low", "cuisines"] == ["Italian", "Chinese"]
    assert df.loc["Budget Low", "budget_band"] == "low"
    assert df.loc["Budget Medium", "budget_band"] == "medium"
    assert df.loc["Budget Edge", "budget_band"] == "medium"
    assert df.loc["Budget High", "budget_band"] == "high"
    assert df.loc["No Cost", "cost_for_two"] is pd.NA
    assert df.loc["No Cost", "budget_band"] == "unknown"
    assert df.loc["Text Cost", "budget_band"] == "unknown"

    cafe = df.loc["Café Unicode"]
    assert cafe["cuisines"] == [] and cafe["rest_types"] == []
    assert bool(cafe["online_order"]) and bool(cafe["book_table"])
    assert cafe["dishes_liked"] == []


def test_duplicate_name_address_keeps_max_votes(cleaned):
    df, _ = cleaned
    toit = df[df["name"] == "Toit"]
    assert len(toit) == 2  # same name, different address stays separate
    main = toit[toit["address"] == "298 100 Feet Rd"].iloc[0]
    assert main["votes"] == 14000
    assert math.isclose(main["rating"], 4.7)
    assert main["cost_for_two"] == 1500
    assert main["dishes_liked"] == ["Pizza", "Beer", "Nachos"]
    assert len(main["review_excerpt"]) <= 400


def test_duplicate_with_equal_votes_is_deterministic(cleaned):
    df, _ = cleaned
    equal = df[df["name"] == "Equal Votes"]
    assert len(equal) == 1
    assert math.isclose(equal.iloc[0]["rating"], 4.0)


def test_missing_required_column_fails_loudly(raw_df):
    with pytest.raises(ValueError, match="cuisines"):
        clean_dataframe(raw_df.drop(columns=["cuisines"]))


def test_facets_are_frequency_sorted_and_case_merged():
    df = pd.DataFrame(
        {
            "locality": ["Indiranagar", "Indiranagar", "indiranagar ", "BTM", ""],
            "city_zone": ["Indiranagar", "Indiranagar", "Indiranagar", "BTM", "BTM"],
            "cuisines": [["North Indian"], ["north indian", "Chinese"], ["Chinese"],
                         ["North Indian"], []],
        }
    )
    facets = build_facets(df)
    assert facets["localities"] == ["Indiranagar", "BTM"]
    assert facets["city_zones"] == ["Indiranagar", "BTM"]
    assert facets["cuisines"] == ["North Indian", "Chinese"]
    assert facets["budget_bands"] == ["low", "medium", "high"]


def test_write_and_load_store_round_trip(tmp_path, raw_df):
    df, _ = clean_dataframe(raw_df)
    parquet_path = tmp_path / "restaurants.parquet"
    facets_path = tmp_path / "facets.json"
    write_outputs(df, parquet_path, facets_path)
    write_outputs(df, parquet_path, facets_path)  # re-run overwrites, no append

    store = RestaurantStore.load(parquet_path, facets_path)
    assert len(store) == len(df)
    assert "Indiranagar" in store.facets["localities"]
    assert "koramangala 5th block" in store.by_locality
    assert "italian" in store.by_cuisine

    toit = store.get(restaurant_id("Toit", "298 100 Feet Rd"))
    assert toit is not None
    assert toit.rating == 4.7 and toit.cost_for_two == 1500 and toit.budget_band == "high"
    assert toit.cuisines == ["Italian", "American", "Pizza"]
    assert isinstance(toit.votes, int)

    fresh = store.get(restaurant_id("Fresh Place", "1 Main St"))
    assert fresh is not None and fresh.rating is None
    assert store.get("does-not-exist") is None


def test_store_missing_parquet_raises_clear_error(tmp_path):
    with pytest.raises(StoreNotReadyError, match="load_hf"):
        RestaurantStore.load(tmp_path / "missing.parquet", tmp_path / "facets.json")
