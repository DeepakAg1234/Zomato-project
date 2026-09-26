"""FastAPI wrapper around the shared restaurant recommendation service."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from time import monotonic

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.models import RecommendationResponse, UserPreferences
from src.services.recommend import preference_hash, recommend
from src.store.restaurant_store import RestaurantStore, StoreNotReadyError

DEFAULT_CACHE_TTL_SECONDS = 60.0
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_LOCAL_UI_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def _cors_settings() -> tuple[list[str], str | None]:
    """Local Vite origins plus optional production origins from the environment."""
    origins = list(_LOCAL_UI_ORIGINS)
    seen = set(origins)
    for origin in os.environ.get("CORS_ORIGINS", "").split(","):
        cleaned = origin.strip()
        if cleaned and cleaned not in seen:
            origins.append(cleaned)
            seen.add(cleaned)
    regex = os.environ.get("CORS_ORIGIN_REGEX", "").strip() or None
    return origins, regex


RecommendationService = Callable[
    [RestaurantStore, UserPreferences],
    RecommendationResponse,
]


class MetaResponse(BaseModel):
    """Dataset-backed values used to build preference forms."""

    localities: list[str]
    city_zones: list[str]
    cuisines: list[str]
    budget_bands: list[str]


class TTLRecommendationCache:
    """Small process-local cache keyed by the non-reversible preference hash."""

    def __init__(self, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS):
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative")
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, tuple[float, RecommendationResponse]] = {}
        self._lock = Lock()

    def get(self, key: str) -> RecommendationResponse | None:
        now = monotonic()
        with self._lock:
            cached = self._items.get(key)
            if cached is None:
                return None
            expires_at, response = cached
            if now >= expires_at:
                self._items.pop(key, None)
                return None
            return response.model_copy(deep=True)

    def set(self, key: str, response: RecommendationResponse) -> None:
        if self.ttl_seconds == 0:
            return
        with self._lock:
            self._items[key] = (
                monotonic() + self.ttl_seconds,
                response.model_copy(deep=True),
            )


def create_app(
    *,
    store: RestaurantStore | None = None,
    recommendation_service: RecommendationService = recommend,
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
) -> FastAPI:
    """Create an API app, optionally injecting a fixture store for tests."""
    api = FastAPI(
        title="Bengaluru Restaurant Finder API",
        version="1.0.0",
        description="Dataset-grounded restaurant recommendations.",
    )
    allow_origins, allow_origin_regex = _cors_settings()
    api.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_origin_regex=allow_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    cache = TTLRecommendationCache(cache_ttl_seconds)
    store_lock = Lock()
    resolved_store = store

    def get_store() -> RestaurantStore:
        nonlocal resolved_store
        if resolved_store is not None:
            return resolved_store
        with store_lock:
            if resolved_store is None:
                try:
                    resolved_store = RestaurantStore.load()
                except StoreNotReadyError as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
        return resolved_store

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/meta", response_model=MetaResponse)
    def meta() -> MetaResponse:
        facets = get_store().facets
        return MetaResponse(
            localities=list(facets.get("localities", [])),
            city_zones=list(facets.get("city_zones", [])),
            cuisines=list(facets.get("cuisines", [])),
            budget_bands=list(facets.get("budget_bands", [])),
        )

    @api.post("/recommendations", response_model=RecommendationResponse)
    def recommendations(preferences: UserPreferences) -> RecommendationResponse:
        key = preference_hash(preferences)
        if cached := cache.get(key):
            return cached

        response = recommendation_service(get_store(), preferences)
        cache.set(key, response)
        return response

    _mount_frontend(api)
    return api


def _mount_frontend(api: FastAPI) -> None:
    """Serve the built web UI from `/` when `frontend/dist` exists."""
    index = _FRONTEND_DIST / "index.html"
    assets = _FRONTEND_DIST / "assets"
    if not index.is_file() or not assets.is_dir():
        return

    @api.get("/", include_in_schema=False)
    def frontend_index() -> FileResponse:
        return FileResponse(index)

    api.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")


app = create_app()
