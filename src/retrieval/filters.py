"""Hard filters and the relaxation ladder (architecture §5.4).

Eligibility is decided here, in code, on cleaned tabular data — never by the
model. Every filter is case-insensitive on the matching key while the store
keeps display casing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from src.models import RelaxationStep, UserPreferences
from src.store.restaurant_store import RestaurantStore

MIN_RESULTS = 3

NEIGHBOURING_BANDS: dict[str, tuple[str, ...]] = {
    "low": ("low", "medium"),
    "medium": ("low", "medium", "high"),
    "high": ("medium", "high"),
}


@dataclass(frozen=True)
class FilterSpec:
    """Resolved filter state. Empty `localities` + `city_zones` means any area."""

    localities: frozenset[str]
    city_zones: frozenset[str]
    budget_bands: frozenset[str]
    cuisines: frozenset[str]
    min_rating: float

    @property
    def any_area(self) -> bool:
        return not self.localities and not self.city_zones


def spec_from_preferences(preferences: UserPreferences) -> FilterSpec:
    return FilterSpec(
        localities=frozenset({preferences.locality.lower()} if preferences.locality else ()),
        city_zones=frozenset({preferences.city_zone.lower()} if preferences.city_zone else ()),
        budget_bands=frozenset({preferences.budget}),
        cuisines=frozenset(c.lower() for c in preferences.cuisines),
        min_rating=preferences.min_rating,
    )


def _rows_from_index(index: dict[str, list[int]], keys: frozenset[str], size: int) -> np.ndarray:
    mask = np.zeros(size, dtype=bool)
    for key in keys:
        rows = index.get(key)
        if rows:
            mask[rows] = True
    return mask


def apply_filters(store: RestaurantStore, spec: FilterSpec) -> np.ndarray:
    """Row positions passing every hard filter, in stable store order."""
    size = len(store)
    mask = np.ones(size, dtype=bool)

    if not spec.any_area:
        mask &= _rows_from_index(store.by_locality, spec.localities, size) | _rows_from_index(
            store.by_city_zone, spec.city_zones, size
        )

    mask &= store.df["budget_band"].isin(spec.budget_bands).to_numpy(dtype=bool)

    if spec.cuisines:
        mask &= _rows_from_index(store.by_cuisine, spec.cuisines, size)

    # A minimum only makes sense against a known rating, so unrated rows drop
    # out as soon as one is asked for. min_rating = 0 keeps them.
    if spec.min_rating > 0:
        rating_ok = (store.df["rating"] >= spec.min_rating).fillna(False)
        mask &= rating_ok.to_numpy(dtype=bool)

    return np.flatnonzero(mask)


def _relax(
    spec: FilterSpec,
    step: RelaxationStep,
    store: RestaurantStore,
    preferences: UserPreferences,
) -> FilterSpec | None:
    """Widened spec for `step`, or None when the step does not apply."""
    if step is RelaxationStep.AREA_TO_CITY_ZONE:
        if not preferences.locality:
            return None
        zones = set(spec.city_zones)
        for locality in spec.localities:
            zones.update(store.zones_by_locality.get(locality, ()))
        if zones == set(spec.city_zones):
            return None
        return replace(spec, city_zones=frozenset(zones))

    if step is RelaxationStep.BUDGET_NEIGHBOURS:
        bands = set(spec.budget_bands)
        for band in spec.budget_bands:
            bands.update(NEIGHBOURING_BANDS.get(band, ()))
        if bands == set(spec.budget_bands):
            return None
        return replace(spec, budget_bands=frozenset(bands))

    if step is RelaxationStep.BUDGET_UNKNOWN:
        return replace(spec, budget_bands=spec.budget_bands | {"unknown"})

    if step is RelaxationStep.CUISINE_DROPPED:
        if not spec.cuisines:
            return None
        return replace(spec, cuisines=frozenset())

    return None


def retrieve_rows(
    store: RestaurantStore, preferences: UserPreferences
) -> tuple[np.ndarray, list[RelaxationStep]]:
    """Filter, widening in `RelaxationStep` order while fewer than `MIN_RESULTS` match.

    A step is only reported when it actually brought in new restaurants, so the
    UI never claims to have expanded a search that found nothing extra.
    `min_rating` is never relaxed: a user who asked for 4.0+ never sees a 3.5.
    """
    spec = spec_from_preferences(preferences)
    rows = apply_filters(store, spec)
    steps: list[RelaxationStep] = []
    if len(rows) >= MIN_RESULTS:
        return rows, steps

    for step in RelaxationStep:
        relaxed = _relax(spec, step, store, preferences)
        if relaxed is None:
            continue
        spec = relaxed
        widened = apply_filters(store, spec)
        if len(widened) > len(rows):
            steps.append(step)
            rows = widened
        if len(rows) >= MIN_RESULTS:
            break

    return rows, steps
