import pytest
from pydantic import ValidationError

from src.models import RelaxationStep, UserPreferences
from src.retrieval.filters import MIN_RESULTS, apply_filters, retrieve_rows, spec_from_preferences
from tests.conftest import build_store, restaurant_row


def prefs(**overrides) -> UserPreferences:
    base = {"locality": "Indiranagar", "budget": "medium"}
    return UserPreferences(**{**base, **overrides})


def matched(store, preferences) -> list[str]:
    rows, _ = retrieve_rows(store, preferences)
    return sorted(store.to_restaurant(int(row)).name for row in rows)


def filtered(store, preferences) -> list[str]:
    rows = apply_filters(store, spec_from_preferences(preferences))
    return sorted(store.to_restaurant(int(row)).name for row in rows)


# --- Validation (edge-case.md P2-V) ---------------------------------------


def test_defaults():
    p = prefs()
    assert p.max_results == 5
    assert p.min_rating == 0.0
    assert p.cuisines == []
    assert p.extra_preferences == ""


@pytest.mark.parametrize(
    "overrides",
    [
        {"budget": "cheap"},
        {"min_rating": -0.1},
        {"min_rating": 5.1},
        {"max_results": 0},
        {"max_results": -1},
        {"max_results": 11},
        {"extra_preferences": "x" * 301},
    ],
)
def test_invalid_preferences_are_rejected(overrides):
    with pytest.raises(ValidationError):
        prefs(**overrides)


def test_area_is_required_unless_any_area_is_explicit():
    with pytest.raises(ValidationError, match="any_area"):
        UserPreferences(budget="medium")
    assert UserPreferences(budget="medium", any_area=True).locality is None


def test_blank_strings_and_cuisines_are_normalized():
    p = prefs(locality=" Indiranagar ", city_zone="   ", cuisines=["Italian", " ", "  Chinese "])
    assert p.locality == "Indiranagar"
    assert p.city_zone is None
    assert p.cuisines == ["Italian", "Chinese"]


def test_min_rating_precision_does_not_change_the_filter(store):
    assert filtered(store, prefs(min_rating=4.0)) == filtered(store, prefs(min_rating=4.00))


# --- Hard filters (P2-H) ---------------------------------------------------


def test_locality_only_ignores_other_zones(store):
    results = filtered(store, prefs())
    assert "Zone Italian" not in results  # same zone, different locality
    assert "Kora Italian" not in results


def test_city_zone_only_covers_every_locality_in_it(store):
    results = filtered(store, prefs(locality=None, city_zone="Indiranagar"))
    assert "Zone Italian" in results and "Trattoria Indira" in results
    assert "BTM Bites" not in results


def test_locality_and_city_zone_are_a_union_not_an_intersection(store):
    """Locked choice for P2-V-10: either area qualifies a restaurant."""
    results = filtered(store, prefs(city_zone="Koramangala"))
    assert "Trattoria Indira" in results and "Kora Italian" in results


def test_unknown_locality_matches_nothing_rather_than_fuzzy_matching(store):
    assert filtered(store, prefs(locality="Whitefield")) == []


def test_any_area_searches_the_whole_city(store):
    results = filtered(store, prefs(locality=None, any_area=True, cuisines=["Italian"]))
    assert "Kora Italian" in results and "Trattoria Indira" in results


def test_cuisine_match_is_case_insensitive_and_any_overlap(store):
    single = filtered(store, prefs(cuisines=["italian"]))
    assert "Pasta Point" in single  # stored lowercase in the fixture
    assert "Trattoria Indira" in single

    either = filtered(store, prefs(cuisines=["Italian", "Chinese"]))
    assert "Wok This Way" in either and "Trattoria Indira" in either


def test_empty_cuisine_list_is_no_constraint(store):
    assert len(filtered(store, prefs())) > len(filtered(store, prefs(cuisines=["Italian"])))


def test_restaurant_without_cuisines_fails_a_cuisine_filter(store):
    assert "No Cuisine Listed" in filtered(store, prefs())
    assert "No Cuisine Listed" not in filtered(store, prefs(cuisines=["Italian"]))


def test_budget_band_is_exact_on_the_first_pass(store):
    results = filtered(store, prefs(cuisines=["Italian"]))
    assert "Cheap Pasta" not in results  # low
    assert "Fine Italia" not in results  # high
    assert "Cost Unknown Cafe" not in results  # unknown cost


@pytest.mark.parametrize(
    "name, included",
    [("Exactly Four", True), ("Just Under", False), ("Brand New Bistro", False)],
)
def test_min_rating_boundary_and_unrated_rows(store, name, included):
    results = filtered(store, prefs(cuisines=["Italian"], min_rating=4.0))
    assert (name in results) is included


def test_unrated_rows_survive_only_when_no_minimum_is_asked_for(store):
    assert "Brand New Bistro" in filtered(store, prefs(cuisines=["Italian"], min_rating=0.0))
    assert "Brand New Bistro" not in filtered(store, prefs(cuisines=["Italian"], min_rating=0.1))


def test_all_four_filters_together(store):
    assert filtered(store, prefs(cuisines=["Italian"], min_rating=4.0)) == [
        "Exactly Four",
        "Olive Counter",
        "Pasta Point",
        "Trattoria Indira",
    ]


def test_impossible_combination_stays_empty_through_every_relaxation(store):
    rows, steps = retrieve_rows(store, prefs(locality="Whitefield", cuisines=["Mexican"]))
    assert len(rows) == 0
    assert steps == []  # nothing was gained, so nothing is claimed


# --- Relaxation (P2-X) -----------------------------------------------------


def test_three_matches_do_not_relax(store):
    preferences = prefs(cuisines=["Italian", "Chinese"], min_rating=4.2)
    rows, steps = retrieve_rows(store, preferences)
    assert len(rows) == MIN_RESULTS == 3
    assert steps == []


def test_two_matches_relax_to_the_city_zone_first(store):
    preferences = prefs(cuisines=["Italian"], min_rating=4.2)
    assert len(filtered(store, preferences)) == 2

    rows, steps = retrieve_rows(store, preferences)
    assert steps == [RelaxationStep.AREA_TO_CITY_ZONE]
    assert matched(store, preferences) == ["Pasta Point", "Trattoria Indira", "Zone Italian"]
    assert len(rows) >= MIN_RESULTS


def test_relaxation_never_admits_a_restaurant_below_min_rating(store):
    preferences = prefs(cuisines=["Italian"], min_rating=4.2)
    rows, _ = retrieve_rows(store, preferences)
    assert all(store.to_restaurant(int(row)).rating >= 4.2 for row in rows)


def test_city_zone_only_search_skips_the_area_step():
    small = build_store(
        [
            restaurant_row("Zone Medium", locality="Old Airport Road", cuisines=["Italian"]),
            restaurant_row("Zone Cheap", locality="Indiranagar", cuisines=["Italian"],
                           cost_for_two=300),
            restaurant_row("Zone Cheaper", locality="Indiranagar", cuisines=["Italian"],
                           cost_for_two=250),
        ]
    )
    _, steps = retrieve_rows(small, prefs(locality=None, city_zone="Indiranagar",
                                          cuisines=["Italian"]))
    assert steps == [RelaxationStep.BUDGET_NEIGHBOURS]


def test_budget_widens_to_neighbouring_bands_then_to_unknown_cost():
    rows = [
        restaurant_row("Solo Medium", cuisines=["Italian"], cost_for_two=700),
        restaurant_row("Cheap One", cuisines=["Italian"], cost_for_two=300),
        restaurant_row("Pricey One", cuisines=["Italian"], cost_for_two=1500),
        restaurant_row("No Price", cuisines=["Italian"], cost_for_two=None),
    ]
    _, steps = retrieve_rows(build_store(rows), prefs(cuisines=["Italian"]))
    assert steps == [RelaxationStep.BUDGET_NEIGHBOURS]

    # Only one priced neighbour exists here, so the search must also take the
    # unpriced row before it reaches three.
    low_only = build_store(rows[:2] + rows[3:])
    preferences = prefs(cuisines=["Italian"])
    _, steps = retrieve_rows(low_only, preferences)
    assert steps == [RelaxationStep.BUDGET_NEIGHBOURS, RelaxationStep.BUDGET_UNKNOWN]
    assert matched(low_only, preferences) == ["Cheap One", "No Price", "Solo Medium"]


def test_cuisine_is_dropped_last(store):
    preferences = prefs(cuisines=["Mexican"], min_rating=4.0)
    rows, steps = retrieve_rows(store, preferences)
    assert steps == [RelaxationStep.CUISINE_DROPPED]
    assert len(rows) >= MIN_RESULTS
