from fastapi.testclient import TestClient

from src.api.app import create_app
from src.models import RecommendationItem, RecommendationResponse


def request_body(**overrides) -> dict:
    return {
        "locality": "Indiranagar",
        "city_zone": None,
        "budget": "medium",
        "cuisines": ["Italian"],
        "min_rating": 4.0,
        "extra_preferences": "family-friendly",
        "max_results": 5,
        **overrides,
    }


def test_health_does_not_load_the_store(monkeypatch):
    def fail_load(*_args, **_kwargs):
        raise AssertionError("health must not load the store")

    monkeypatch.setattr("src.store.restaurant_store.RestaurantStore.load", fail_load)
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_deployed_vercel_origin_by_default(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    client = TestClient(create_app())

    production = client.options(
        "/health",
        headers={
            "Origin": "https://zomato-project-weld.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    preview = client.options(
        "/health",
        headers={
            "Origin": "https://zomato-project-git-main-team.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert (
        production.headers["access-control-allow-origin"]
        == "https://zomato-project-weld.vercel.app"
    )
    assert (
        preview.headers["access-control-allow-origin"]
        == "https://zomato-project-git-main-team.vercel.app"
    )


def test_cors_allows_localhost_configured_origins_and_preview_regex(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.vercel.app, https://custom.example",
    )
    monkeypatch.setenv("CORS_ORIGIN_REGEX", r"https://finder.*\.vercel\.app")
    client = TestClient(create_app())

    def preflight(origin: str, method: str = "GET"):
        return client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

    local = preflight("http://localhost:5173")
    production = preflight("https://app.vercel.app", "POST")
    preview = preflight("https://finder-git-main-team.vercel.app", "POST")
    blocked = preflight("https://evil.example")

    assert local.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert production.headers["access-control-allow-origin"] == "https://app.vercel.app"
    assert (
        preview.headers["access-control-allow-origin"]
        == "https://finder-git-main-team.vercel.app"
    )
    assert "access-control-allow-origin" not in blocked.headers
    assert "GET" in production.headers["access-control-allow-methods"]
    assert "POST" in production.headers["access-control-allow-methods"]


def test_meta_returns_only_dataset_backed_facets(store):
    response = TestClient(create_app(store=store)).get("/meta")

    assert response.status_code == 200
    assert response.json() == store.facets
    assert "Indiranagar" in response.json()["localities"]
    assert response.json()["budget_bands"] == ["low", "medium", "high"]


def test_recommendations_matches_the_documented_contract_and_uses_cache(store):
    calls = []

    def recommendation_service(active_store, preferences):
        calls.append(preferences)
        restaurant = active_store.get(active_store.df.iloc[0]["id"])
        assert restaurant is not None
        return RecommendationResponse(
            summary="A strong match in Indiranagar.",
            relaxation_applied=None,
            engine="llm",
            results=[
                RecommendationItem(
                    id=restaurant.id,
                    rank=1,
                    name=restaurant.name,
                    cuisines=restaurant.cuisines,
                    rating=restaurant.rating,
                    votes=restaurant.votes,
                    cost_for_two=restaurant.cost_for_two,
                    locality=restaurant.locality,
                    online_order=restaurant.online_order,
                    book_table=restaurant.book_table,
                    explanation="Matches the requested cuisine and budget.",
                    url=restaurant.url,
                )
            ],
        )

    client = TestClient(
        create_app(store=store, recommendation_service=recommendation_service)
    )
    first = client.post("/recommendations", json=request_body())
    second = client.post("/recommendations", json=request_body())

    assert first.status_code == 200
    assert second.json() == first.json()
    assert len(calls) == 1
    payload = first.json()
    assert payload["engine"] == "llm"
    assert payload["results"][0]["rank"] == 1
    assert payload["results"][0]["name"] == "Trattoria Indira"
    assert payload["results"][0]["cost_for_two"] == 800
    assert payload["results"][0]["explanation"]


def test_recommendations_rejects_an_invalid_request_without_calling_service(store):
    def must_not_run(*_args):
        raise AssertionError("service must not be called")

    client = TestClient(create_app(store=store, recommendation_service=must_not_run))
    response = client.post(
        "/recommendations",
        json=request_body(budget="cheap"),
    )

    assert response.status_code == 422


def test_cache_can_be_disabled(store):
    calls = 0

    def recommendation_service(_store, _preferences):
        nonlocal calls
        calls += 1
        return RecommendationResponse(engine="none", results=[], message="No matches.")

    client = TestClient(
        create_app(
            store=store,
            recommendation_service=recommendation_service,
            cache_ttl_seconds=0,
        )
    )
    client.post("/recommendations", json=request_body())
    client.post("/recommendations", json=request_body())

    assert calls == 2
