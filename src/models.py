"""Canonical data models for the restaurant recommendation system.

Field names match architecture §4.3 (Restaurant) and §5.3 (UserPreferences).
Retrieval output (§5.4) is modelled here too so services, UI, and the LLM layer
share one vocabulary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EXTRA_PREFERENCES_MAX_CHARS = 300
MAX_RESULTS_LIMIT = 10

BudgetBand = Literal["low", "medium", "high", "unknown"]
BudgetPreference = Literal["low", "medium", "high"]


class Restaurant(BaseModel):
    """Canonical restaurant record after cleaning (architecture §4.3)."""

    id: str
    name: str
    locality: str
    city_zone: str
    address: str
    cuisines: list[str]
    rest_types: list[str]
    listing_type: str
    cost_for_two: int | None = None
    budget_band: BudgetBand = "unknown"
    rating: float | None = None
    votes: int = 0
    online_order: bool = False
    book_table: bool = False
    dishes_liked: list[str] = Field(default_factory=list)
    review_excerpt: str | None = None
    url: str | None = None


class UserPreferences(BaseModel):
    """User preference schema for retrieval and ranking (architecture §5.3).

    Rules locked here (and in `tests/test_filters.py`):

    - `locality` and `city_zone` are a union, not an intersection; searching
      without either needs `any_area=True` so a city-wide search is deliberate.
    - `cuisines=[]` means "no cuisine constraint", not "matches nothing".
    - Out-of-range `min_rating` / `max_results` are rejected, not clamped.
    """

    locality: str | None = None
    city_zone: str | None = None
    budget: BudgetPreference
    cuisines: list[str] = Field(default_factory=list)
    min_rating: float = Field(default=0.0, ge=0.0, le=5.0)
    extra_preferences: str = Field(default="", max_length=EXTRA_PREFERENCES_MAX_CHARS)
    max_results: int = Field(default=5, ge=1, le=MAX_RESULTS_LIMIT)
    any_area: bool = False

    @field_validator("locality", "city_zone", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("cuisines", mode="before")
    @classmethod
    def _drop_blank_cuisines(cls, value: object) -> object:
        if isinstance(value, list):
            return [c.strip() for c in value if isinstance(c, str) and c.strip()]
        return value

    @model_validator(mode="after")
    def _require_area(self) -> UserPreferences:
        if not self.locality and not self.city_zone and not self.any_area:
            raise ValueError(
                "Set locality or city_zone, or pass any_area=True to search the whole city."
            )
        return self


class RelaxationStep(StrEnum):
    """Ordered ways retrieval widens a search that matched fewer than 3 rows."""

    AREA_TO_CITY_ZONE = "area_expanded_to_city_zone"
    BUDGET_NEIGHBOURS = "budget_widened_to_neighbouring_bands"
    BUDGET_UNKNOWN = "budget_includes_unknown_cost"
    CUISINE_DROPPED = "cuisine_constraint_dropped"

    @property
    def description(self) -> str:
        return _RELAXATION_DESCRIPTIONS[self]


_RELAXATION_DESCRIPTIONS = {
    RelaxationStep.AREA_TO_CITY_ZONE: "widened the area to the surrounding city zone",
    RelaxationStep.BUDGET_NEIGHBOURS: "included neighbouring budget bands",
    RelaxationStep.BUDGET_UNKNOWN: "included places with no listed cost",
    RelaxationStep.CUISINE_DROPPED: "dropped the cuisine filter",
}


class Candidate(BaseModel):
    """A restaurant that passed the hard filters, with its retrieval score.

    Carries no phone number — nothing on this object may reach the LLM prompt
    that is not safe to send.
    """

    restaurant: Restaurant
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Everything the LLM phase (and a no-LLM demo) needs from retrieval."""

    candidates: list[Candidate] = Field(default_factory=list)
    relaxation_steps: list[RelaxationStep] = Field(default_factory=list)
    matched_count: int = 0
    retrieval_ms: float = 0.0
    engine: str = "heuristic"

    @property
    def relaxation_applied(self) -> str | None:
        """Human-readable note for the UI, or None when nothing was relaxed."""
        if not self.relaxation_steps:
            return None
        return "We " + ", then ".join(step.description for step in self.relaxation_steps) + "."


class RecommendationItem(BaseModel):
    """A display-ready card grounded in a restaurant from the local store."""

    id: str
    rank: int = Field(ge=1)
    name: str
    cuisines: list[str]
    rating: float | None = None
    votes: int = 0
    cost_for_two: int | None = None
    locality: str
    online_order: bool = False
    book_table: bool = False
    explanation: str
    url: str | None = None


class RecommendationResponse(BaseModel):
    """Final response shared by the UI and the optional HTTP API."""

    summary: str | None = None
    relaxation_applied: str | None = None
    engine: Literal["llm", "fallback", "none"]
    results: list[RecommendationItem] = Field(default_factory=list)
    message: str | None = None
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
