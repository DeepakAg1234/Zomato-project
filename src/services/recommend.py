"""Recommendation orchestration: validate → retrieve → rank → ground."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Mapping
from time import perf_counter

from src.llm.client import ChatClient, GroqLLMClient
from src.llm.parser import (
    LLMParseError,
    fallback_results,
    parse_recommendations,
)
from src.llm.prompt import build_messages
from src.models import RecommendationResponse, RetrievalResult, UserPreferences
from src.retrieval.filters import retrieve_rows
from src.retrieval.scorer import DEFAULT_CANDIDATE_CAP, score_rows
from src.store.restaurant_store import RestaurantStore

ENGINE_HEURISTIC = "heuristic"
EMPTY_MESSAGE = "No restaurants matched these preferences. Try relaxing a filter."
FALLBACK_SUMMARY = "Recommendations ranked using restaurant ratings and popularity."

logger = logging.getLogger(__name__)


def preference_hash(preferences: UserPreferences) -> str:
    """Short stable digest for logging and (Phase 5) caching."""
    canonical = preferences.model_copy(update={"cuisines": sorted(preferences.cuisines)})
    return hashlib.sha1(canonical.model_dump_json().encode("utf-8")).hexdigest()[:12]


def retrieve_candidates(
    store: RestaurantStore,
    preferences: UserPreferences | Mapping[str, object],
    *,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
) -> RetrievalResult:
    """Return the deterministic Phase 2 shortlist."""
    if not isinstance(preferences, UserPreferences):
        preferences = UserPreferences.model_validate(preferences)

    started = perf_counter()
    rows, steps = retrieve_rows(store, preferences)
    candidates = score_rows(store, rows, preferences, candidate_cap=candidate_cap)
    retrieval_ms = (perf_counter() - started) * 1000

    result = RetrievalResult(
        candidates=candidates,
        relaxation_steps=steps,
        matched_count=len(rows),
        retrieval_ms=round(retrieval_ms, 2),
        engine=ENGINE_HEURISTIC,
    )
    logger.info(
        "retrieval prefs=%s matched=%d candidates=%d relaxation=%s retrieval_ms=%.1f",
        preference_hash(preferences),
        result.matched_count,
        len(result.candidates),
        [step.value for step in steps] or None,
        result.retrieval_ms,
    )
    return result


def _repair_messages(
    messages: list[dict[str, str]],
    invalid_response: str,
) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": invalid_response},
        {
            "role": "user",
            "content": (
                "Repair the previous response. Return only valid JSON matching the required "
                "schema, and use only candidate ids from my candidate list."
            ),
        },
    ]


def _log_completion(
    preferences: UserPreferences,
    retrieval: RetrievalResult,
    response: RecommendationResponse,
) -> None:
    logger.info(
        "recommend prefs=%s candidates=%d retrieval_ms=%.1f llm_ms=%.1f engine=%s",
        preference_hash(preferences),
        len(retrieval.candidates),
        response.retrieval_ms,
        response.llm_ms,
        response.engine,
    )


def recommend(
    store: RestaurantStore,
    preferences: UserPreferences | Mapping[str, object],
    *,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
    client: ChatClient | None = None,
) -> RecommendationResponse:
    """Return grounded recommendation cards, falling back on any LLM failure."""
    if not isinstance(preferences, UserPreferences):
        preferences = UserPreferences.model_validate(preferences)

    retrieval = retrieve_candidates(store, preferences, candidate_cap=candidate_cap)
    if not retrieval.candidates:
        response = RecommendationResponse(
            engine="none",
            results=[],
            message=EMPTY_MESSAGE,
            relaxation_applied=retrieval.relaxation_applied,
            retrieval_ms=retrieval.retrieval_ms,
        )
        _log_completion(preferences, retrieval, response)
        return response

    messages = build_messages(preferences, retrieval.candidates)
    llm_started = perf_counter()
    try:
        active_client = client if client is not None else GroqLLMClient.from_env()
        raw = active_client.complete(messages)
        try:
            parsed = parse_recommendations(
                raw,
                retrieval.candidates,
                preferences.max_results,
            )
        except LLMParseError:
            repaired = active_client.complete(_repair_messages(messages, raw))
            parsed = parse_recommendations(
                repaired,
                retrieval.candidates,
                preferences.max_results,
            )
        llm_ms = round((perf_counter() - llm_started) * 1000, 2)
        response = RecommendationResponse(
            summary=parsed.summary,
            relaxation_applied=retrieval.relaxation_applied,
            engine="llm",
            results=parsed.results,
            retrieval_ms=retrieval.retrieval_ms,
            llm_ms=llm_ms,
        )
    except Exception as exc:
        llm_ms = round((perf_counter() - llm_started) * 1000, 2)
        logger.warning("LLM ranking failed (%s); using fallback", type(exc).__name__)
        response = RecommendationResponse(
            summary=FALLBACK_SUMMARY,
            relaxation_applied=retrieval.relaxation_applied,
            engine="fallback",
            results=fallback_results(retrieval.candidates, preferences.max_results),
            retrieval_ms=retrieval.retrieval_ms,
            llm_ms=llm_ms,
        )

    _log_completion(preferences, retrieval, response)
    return response
