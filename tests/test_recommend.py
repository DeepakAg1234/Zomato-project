import pytest
from pydantic import ValidationError

from src.models import UserPreferences
from src.retrieval.scorer import MAX_CANDIDATE_CAP
from src.services.recommend import preference_hash, recommend, retrieve_candidates


def prefs(**overrides) -> dict:
    return {"locality": "Indiranagar", "budget": "medium", **overrides}


class StubClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_retrieval_helper_keeps_the_phase_2_shortlist(store):
    result = retrieve_candidates(store, prefs(cuisines=["Italian"], min_rating=4.0))
    assert result.engine == "heuristic"
    assert result.matched_count == 4
    assert 0 < len(result.candidates) <= MAX_CANDIDATE_CAP
    assert result.candidates[0].restaurant.name == "Trattoria Indira"


def test_accepts_a_validated_model_or_a_raw_mapping(store):
    preferences = UserPreferences(**prefs(cuisines=["Italian"]))
    assert [c.restaurant.id for c in retrieve_candidates(store, preferences).candidates] == [
        c.restaurant.id
        for c in retrieve_candidates(store, prefs(cuisines=["Italian"])).candidates
    ]


def test_invalid_preferences_fail_before_any_retrieval(store):
    with pytest.raises(ValidationError):
        recommend(store, prefs(budget="cheap"))


def test_relaxation_is_reported_in_plain_language(store):
    result = retrieve_candidates(store, prefs(cuisines=["Italian"], min_rating=4.2))
    assert "city zone" in result.relaxation_applied
    assert len(result.candidates) >= 3


def test_empty_retrieval_does_not_call_client(store):
    client = StubClient(AssertionError("must not be called"))
    result = recommend(
        store,
        prefs(locality="Whitefield", cuisines=["Mexican"]),
        client=client,
    )
    assert result.engine == "none"
    assert result.results == []
    assert result.message
    assert client.calls == []


def test_same_preferences_always_yield_the_same_candidate_ids(store):
    first = retrieve_candidates(
        store, prefs(cuisines=["Italian"], extra_preferences="family-friendly")
    )
    second = retrieve_candidates(
        store, prefs(cuisines=["Italian"], extra_preferences="family-friendly")
    )
    assert [c.restaurant.id for c in first.candidates] == [
        c.restaurant.id for c in second.candidates
    ]


def test_preference_hash_ignores_cuisine_order(store):
    a = UserPreferences(**prefs(cuisines=["Italian", "Chinese"]))
    b = UserPreferences(**prefs(cuisines=["Chinese", "Italian"]))
    assert preference_hash(a) == preference_hash(b)
    assert preference_hash(a) != preference_hash(UserPreferences(**prefs(cuisines=["Italian"])))


def test_valid_llm_response_returns_grounded_cards_in_model_order(store):
    preferences = UserPreferences(**prefs(cuisines=["Italian"], max_results=2))
    candidates = retrieve_candidates(store, preferences).candidates
    first_id = candidates[1].restaurant.id
    second_id = candidates[0].restaurant.id
    client = StubClient(
        (
            '{"summary":"Two good fits","recommendations":['
            f'{{"id":"{second_id}","rank":2,"explanation":"Strong rating."}},'
            f'{{"id":"{first_id}","rank":1,"explanation":"Fits your cuisine."}}'
            "]}"
        )
    )

    result = recommend(store, preferences, client=client)

    assert result.engine == "llm"
    assert result.summary == "Two good fits"
    assert [item.id for item in result.results] == [first_id, second_id]
    assert [item.rank for item in result.results] == [1, 2]
    assert result.results[0].rating == candidates[1].restaurant.rating


def test_timeout_returns_heuristic_fallback_cards(store):
    result = recommend(
        store,
        prefs(cuisines=["Italian"], max_results=3),
        client=StubClient(TimeoutError()),
    )
    assert result.engine == "fallback"
    assert len(result.results) == 3
    assert all(item.explanation for item in result.results)


def test_invalid_json_gets_one_repair_call(store):
    candidate = retrieve_candidates(store, prefs(cuisines=["Italian"])).candidates[0]
    client = StubClient(
        "not json",
        (
            '{"summary":null,"recommendations":'
            f'[{{"id":"{candidate.restaurant.id}","rank":1,"explanation":"Grounded."}}]'
            "}"
        ),
    )
    result = recommend(store, prefs(cuisines=["Italian"], max_results=1), client=client)
    assert result.engine == "llm"
    assert len(client.calls) == 2
