"""Cleaning rules that turn raw Zomato rows into canonical restaurant records.

Rules follow architecture §4.4. Every parser is a pure function so it can be
unit-tested without Hugging Face.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd

REVIEW_EXCERPT_MAX_CHARS = 400
LOW_BUDGET_MAX = 400
MEDIUM_BUDGET_MAX = 1000

REQUIRED_RAW_COLUMNS = ("name", "location", "cuisines")

RAW_TO_CANONICAL = {
    "name": "name",
    "location": "locality",
    "listed_in(city)": "city_zone",
    "address": "address",
    "cuisines": "cuisines",
    "rest_type": "rest_types",
    "listed_in(type)": "listing_type",
    "approx_cost(for two people)": "cost_for_two",
    "rate": "rating",
    "votes": "votes",
    "online_order": "online_order",
    "book_table": "book_table",
    "dish_liked": "dishes_liked",
    "reviews_list": "review_excerpt",
    "url": "url",
}

CANONICAL_COLUMNS = [
    "id",
    "name",
    "locality",
    "city_zone",
    "address",
    "cuisines",
    "rest_types",
    "listing_type",
    "cost_for_two",
    "budget_band",
    "rating",
    "votes",
    "online_order",
    "book_table",
    "dishes_liked",
    "review_excerpt",
    "url",
]

_RATING_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:/\s*5(?:\.0+)?)?\s*$")
_REVIEW_MARKERS_RE = re.compile(r"\(?'?Rated\s+\d(?:\.\d)?'?,?\s*|RATED\\n|\\n|\\x[0-9a-fA-F]{2}")
_WHITESPACE_RE = re.compile(r"\s+")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return value is pd.NA or value is pd.NaT


def clean_text(value: Any) -> str:
    """Return a trimmed string, or "" for missing values."""
    if _is_missing(value):
        return ""
    return _WHITESPACE_RE.sub(" ", str(value)).strip()


def parse_rating(value: Any) -> float | None:
    """`4.1/5` → 4.1; `NEW`, `-`, empty, garbage, or out of [0, 5] → None."""
    if _is_missing(value):
        return None
    if isinstance(value, (int, float)):
        rating = float(value)
    else:
        match = _RATING_RE.match(str(value))
        if not match:
            return None
        rating = float(match.group(1))
    if not 0.0 <= rating <= 5.0:
        return None
    return rating


def parse_cost(value: Any) -> int | None:
    """`"1,200"` / `"₹1,200.00"` → 1200. Missing, non-numeric, or ≤ 0 → None."""
    if _is_missing(value):
        return None
    if isinstance(value, (int, float)):
        cost = float(value)
    else:
        stripped = re.sub(r"[₹,\s]", "", str(value))
        stripped = re.sub(r"^(rs\.?|inr)", "", stripped, flags=re.IGNORECASE)
        try:
            cost = float(stripped)
        except ValueError:
            return None
    if math.isnan(cost) or cost <= 0:
        return None
    return int(round(cost))


def budget_band(cost_for_two: int | None) -> str:
    if cost_for_two is None:
        return "unknown"
    if cost_for_two <= LOW_BUDGET_MAX:
        return "low"
    if cost_for_two <= MEDIUM_BUDGET_MAX:
        return "medium"
    return "high"


def split_list(value: Any) -> list[str]:
    """Split a comma-separated field, trimming and dropping empty tokens."""
    if _is_missing(value):
        return []
    items = [clean_text(part) for part in str(value).split(",")]
    return [item for item in items if item]


def parse_bool(value: Any) -> bool:
    """`Yes`/`No` in any case → bool; anything else → False."""
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"yes", "true", "y", "1"}


def parse_votes(value: Any) -> int:
    if _is_missing(value):
        return 0
    try:
        votes = int(float(str(value).replace(",", "").strip()))
    except ValueError:
        return 0
    return max(votes, 0)


def review_excerpt(value: Any, max_chars: int = REVIEW_EXCERPT_MAX_CHARS) -> str | None:
    """Short, readable excerpt of the raw `reviews_list` blob (≤ max_chars)."""
    if _is_missing(value):
        return None
    head = str(value)[: max_chars * 4]
    text = _REVIEW_MARKERS_RE.sub(" ", head)
    text = re.sub(r"[\[\]()\"']", " ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip(" ,")
    if not text:
        return None
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def restaurant_id(name: str, address: str) -> str:
    """Stable id from normalized name + address, so re-ingest keeps the same ids."""
    key = f"{name.strip().lower()}|{address.strip().lower()}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CleanStats:
    raw_rows: int
    cleaned_rows: int
    deduped_rows: int


def clean_dataframe(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleanStats]:
    """Map raw columns to the canonical schema, clean values, and dedupe.

    Rows without a name are dropped. Duplicates on name + address keep the row
    with the most votes (ties broken by rating, then original order).
    """
    missing = [col for col in REQUIRED_RAW_COLUMNS if col not in raw.columns]
    if missing:
        raise ValueError(f"Raw dataset is missing required columns: {missing}")

    def column(raw_name: str) -> pd.Series:
        if raw_name in raw.columns:
            return raw[raw_name]
        return pd.Series([None] * len(raw), index=raw.index, dtype=object)

    df = pd.DataFrame(index=raw.index)
    df["name"] = column("name").map(clean_text)
    df["locality"] = column("location").map(clean_text)
    df["city_zone"] = column("listed_in(city)").map(clean_text)
    df["address"] = column("address").map(clean_text)
    df["cuisines"] = column("cuisines").map(split_list)
    df["rest_types"] = column("rest_type").map(split_list)
    df["listing_type"] = column("listed_in(type)").map(clean_text)
    df["cost_for_two"] = column("approx_cost(for two people)").map(parse_cost).astype("Int64")
    df["budget_band"] = df["cost_for_two"].map(
        lambda cost: budget_band(None if _is_missing(cost) else int(cost))
    )
    df["rating"] = column("rate").map(parse_rating).astype("Float64")
    df["votes"] = column("votes").map(parse_votes).astype("int64")
    df["online_order"] = column("online_order").map(parse_bool).astype(bool)
    df["book_table"] = column("book_table").map(parse_bool).astype(bool)
    df["dishes_liked"] = column("dish_liked").map(split_list)
    df["review_excerpt"] = column("reviews_list").map(review_excerpt)
    df["url"] = column("url").map(lambda v: clean_text(v).split("?", 1)[0] or None)

    df = df[df["name"] != ""]
    cleaned_rows = len(df)

    df["id"] = [restaurant_id(n, a) for n, a in zip(df["name"], df["address"])]
    df["_order"] = range(len(df))
    df = df.sort_values(
        ["votes", "rating", "_order"],
        ascending=[False, False, True],
        na_position="last",
        kind="mergesort",
    )
    df = df.drop_duplicates(subset="id", keep="first")
    df = df.sort_values("_order", kind="mergesort").drop(columns="_order")
    df = df[CANONICAL_COLUMNS].reset_index(drop=True)

    return df, CleanStats(raw_rows=len(raw), cleaned_rows=cleaned_rows, deduped_rows=len(df))


def _canonical_labels(values: list[str]) -> list[str]:
    """Collapse labels differing only by case/space; order by frequency.

    The display label for each group is its most common spelling.
    """
    groups: dict[str, Counter[str]] = {}
    for value in values:
        label = clean_text(value)
        if label:
            groups.setdefault(label.lower(), Counter())[label] += 1
    ranked = sorted(
        groups.values(),
        key=lambda counts: (-sum(counts.values()), counts.most_common(1)[0][0].lower()),
    )
    return [counts.most_common(1)[0][0] for counts in ranked]


def build_facets(df: pd.DataFrame) -> dict[str, list[str]]:
    """Frequency-sorted facet lists for UI dropdowns and `GET /meta`."""
    return {
        "localities": _canonical_labels(df["locality"].tolist()),
        "city_zones": _canonical_labels(df["city_zone"].tolist()),
        "cuisines": _canonical_labels([c for items in df["cuisines"] for c in items]),
        "budget_bands": ["low", "medium", "high"],
    }
