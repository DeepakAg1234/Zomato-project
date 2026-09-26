import json

import pytest

from src.llm.parser import LLMParseError, parse_recommendations
from src.llm.prompt import build_messages
from src.models import UserPreferences
from src.services.recommend import retrieve_candidates


def preferences(**overrides):
    return UserPreferences(
        locality="Indiranagar",
        budget="medium",
        cuisines=["Italian"],
        **overrides,
    )


def test_parser_drops_unknown_ids_sorts_and_deduplicates(store):
    candidates = retrieve_candidates(store, preferences()).candidates
    first_id = candidates[0].restaurant.id
    second_id = candidates[1].restaurant.id
    raw = json.dumps(
        {
            "summary": "Grounded choices",
            "recommendations": [
                {"id": "invented-id", "rank": 1, "explanation": "Fake"},
                {"id": second_id, "rank": 3, "explanation": "Second"},
                {"id": first_id, "rank": 2, "explanation": "First"},
                {"id": first_id, "rank": 4, "explanation": "Duplicate"},
            ],
        }
    )

    parsed = parse_recommendations(raw, candidates, max_results=2)

    assert [item.id for item in parsed.results] == [first_id, second_id]
    assert [item.rank for item in parsed.results] == [1, 2]


def test_parser_accepts_fenced_json_and_backfills_short_output(store):
    candidates = retrieve_candidates(store, preferences()).candidates
    raw = (
        "```json\n"
        + json.dumps(
            {
                "recommendations": [
                    {"id": candidates[1].restaurant.id, "explanation": "A fit"}
                ]
            }
        )
        + "\n```\nExtra commentary"
    )
    parsed = parse_recommendations(raw, candidates, max_results=3)
    assert len(parsed.results) == 3
    assert parsed.results[0].id == candidates[1].restaurant.id
    assert parsed.results[1].explanation


def test_all_unknown_ids_are_rejected(store):
    candidates = retrieve_candidates(store, preferences()).candidates
    with pytest.raises(LLMParseError):
        parse_recommendations(
            '{"recommendations":[{"id":"fake","rank":1,"explanation":"No"}]}',
            candidates,
            max_results=5,
        )


def test_prompt_contains_only_allowlisted_candidate_fields(store):
    candidates = retrieve_candidates(store, preferences()).candidates
    messages = build_messages(preferences(max_results=5), candidates)
    payload = json.loads(messages[1]["content"])
    candidate = payload["candidates"][0]

    assert set(candidate) == {
        "id",
        "name",
        "locality",
        "cuisines",
        "rating",
        "votes",
        "cost_for_two",
        "rest_types",
        "online_order",
        "book_table",
        "dishes_liked",
        "review_excerpt",
    }
    assert len(payload["candidates"]) == len(candidates)
    assert "exactly 5" in payload["task"]
