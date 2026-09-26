# Implementation Plan

Phase-wise build plan for the AI-powered restaurant recommendation system.

**Sources:** [problemStatement.md](./problemStatement.md) · [architecture.md](./architecture.md)

**Rule that never changes:** hard filters and scoring run in code on cleaned tabular data. The LLM only ranks a closed set of ≤15 candidates and writes explanations. The full ~52k-row dataset is never sent to the model.

---

## How to use this plan

| Phase | Problem-statement step | Architecture | Demoable outcome |
| --- | --- | --- | --- |
| 0 | — | Repo + config | Runnable Python project |
| 1 | Data ingestion | P0 Ingest | Parquet + facet lists |
| 2 | User input schema + integration (filter) | P1 Retrieval | Deterministic shortlist |
| 3 | Integration (prompt) + recommendation engine | P2 LLM | Ranked list with explanations |
| 4 | Output display | P3 UI | End-to-end Streamlit demo |
| 5 | Polish | P4 | Tests, README, optional FastAPI |

Do not start a phase until the previous phase’s **exit criteria** pass. Phase 2 is already a useful product; Phase 3 is what makes it AI-powered.

**v1 out of scope:** live Zomato API, bookings, accounts, embeddings/vector search, cities not in the Hugging Face file.

---

## Phase 0 — Project skeleton

**Goal:** A Python 3.11+ repo that matches the architecture layout and can run ingest later without rework.

### Tasks

1. Create the folder layout from architecture §3 (`src/ingest`, `src/store`, `src/retrieval`, `src/llm`, `src/services`, `src/ui`, `src/api`, `data/raw`, `data/processed`, `tests`).
2. Add `requirements.txt` (pin versions): `datasets`, `pandas`, `pyarrow`, `python-dotenv`, `pydantic`, the official `groq` Python SDK, `streamlit`, `fastapi`, `uvicorn` (FastAPI unused until Phase 5).
3. Add `.env.example` with `GROQ_API_KEY`, `GROQ_MODEL=openai/gpt-oss-120b`, `GROQ_TIMEOUT_SECONDS=20`. Add `.gitignore` for `.env`, `data/raw/`, `__pycache__/`, `.venv/`.
4. Add empty `__init__.py` files and a `src` package path so `python -m src.ingest.load_hf` will work in Phase 1.
5. Add a shared `src/models.py` (or `src/schemas.py`) stub for `Restaurant` and `UserPreferences` field names from architecture §4.3 and §5.3 — types only, no logic yet.

### Deliverables

- Layout on disk
- `requirements.txt`, `.env.example`, `.gitignore`
- Pydantic (or dataclass) models for `Restaurant` and `UserPreferences`

### Exit criteria

- `python -c "from src.models import Restaurant, UserPreferences"` succeeds in a fresh venv
- `.env` is not tracked by git

### Tests

- None required beyond import smoke check

---

## Phase 1 — Data ingestion (P0)

**Goal:** Load the Hugging Face dataset once, clean it into the canonical restaurant model, persist parquet, and expose facet lists.

**Maps to:** problem statement *Data Ingestion*.

### Tasks

1. **Load** `ManikaSaini/zomato-restaurant-recommendation`, split `train` (~51.7k rows). Cache under `data/raw/` if the library supports it so re-runs are offline.
2. **Map raw columns** (architecture §4.2) into canonical fields (§4.3). Skip `menu_item`. Truncate `reviews_list` to ≤400 characters → `review_excerpt`. Do **not** persist phone into prompt-facing records (keep off the LLM path; optional omit from parquet).
3. **Clean** per §4.4:
   - Parse `rate` (`4.1/5` → `4.1`; `NEW` / `-` / empty → `null`)
   - Parse `approx_cost(for two people)` (strip commas → int)
   - Split `cuisines` and `rest_type` on commas
   - Yes/No → bool for `online_order`, `book_table`
   - Deduplicate `name` + `address`, keep highest `votes`
   - Assign `budget_band`: low ≤400, medium 401–1000, high >1000, else `unknown`
   - Stable `id` (hash of name + address, or row index)
4. **Write** `data/processed/restaurants.parquet` (overwrite if exists).
5. **Facets:** unique `locality`, `city_zone`, and cuisine strings (frequency-sorted). Save as JSON next to parquet or compute in the store on load.
6. **CLI:** `python -m src.ingest.load_hf` prints row counts: raw → after clean → after dedupe.

### Files

- `src/ingest/load_hf.py`
- `src/ingest/clean.py`
- `src/store/restaurant_store.py` (load parquet + facets; in-memory pandas)

### Exit criteria

- Parquet exists and loads in seconds
- Spot-check: `rating` is float or null; `cost_for_two` is int or null; `cuisines` is a list
- Facet localities look like Bangalore areas (Indiranagar, Koramangala, …), **not** a Delhi/Bangalore metro list
- Ingest is **not** invoked on every recommendation request

### Tests (`tests/test_clean.py`)

Use a **fixture of ~20 fake rows**, not Hugging Face:

- `4.1/5` → 4.1; `NEW` → null
- `"1,200"` → 1200
- cuisine split and trim
- duplicate name+address keeps max votes
- budget band boundaries (400 → low, 401 → medium, 1001 → high)

---

## Phase 2 — Preferences, filters, scoring (P1)

**Goal:** Given user preferences, return a scored candidate shortlist of K = 8–15 restaurants. No LLM.

**Maps to:** problem statement *User Input* (schema) + *Integration Layer* (filter and prepare).

### Tasks

1. **Validate** `UserPreferences`:
   - `budget` ∈ {low, medium, high}
   - `min_rating` ∈ [0, 5]
   - `extra_preferences` ≤ ~300 chars
   - `max_results` default 5, max 10
   - Prefer requiring `locality` or `city_zone`; allow “any area” only with an explicit flag/warning
2. **Hard filters** (`src/retrieval/filters.py`):
   - Area: locality **or** city_zone match
   - Budget band match
   - Cuisine overlap (case-insensitive, any requested cuisine)
   - `rating >= min_rating`; drop null ratings when min_rating is set
3. **Relaxation** if result count **< 3**, in order:
   1. Expand locality to its `city_zone` (if locality was set)
   2. Include neighbouring budget band
   3. Drop cuisine constraint; keep area + rating  
   Record `relaxation_applied` as a string or enum for the UI.
4. **Score** remaining rows (`src/retrieval/scorer.py`) per architecture:

   `0.45 * norm(rating) + 0.25 * norm(log1p(votes)) + 0.20 * cuisine_overlap + 0.10 * extra_preference_heuristic`

   Heuristic keywords: family-friendly, quick/fast, date/romantic, cafe/outdoor against `rest_types`, `listing_type`, `dishes_liked`, `book_table`, `online_order`.
5. **Cap** at K = 12 (configurable, 8–15). Slice to `max_results` only **after** the LLM phase; retrieval always returns K for the model.
6. **Orchestrator stub** `src/services/recommend.py`: validate → retrieve → return candidates + `relaxation_applied`. `engine` not set yet (or `"heuristic"`).

### Exit criteria

- Same preferences always yield the same candidate ids (deterministic)
- A query with an impossible cuisine in a tiny area returns empty or a recorded relaxation
- Candidate payload for a later prompt would be ≤15 rows
- Phone numbers never appear on candidate objects used for ranking

### Tests (`tests/test_filters.py`, `tests/test_scorer.py`)

Fixture store of ~20 restaurants:

- All four hard filters in combination
- Empty set when nothing matches
- Relaxation fires only below 3 and is recorded
- Higher rating + more votes scores above a weak match when cuisine overlap is equal
- Keyword “quick service” boosts Quick Bites vs fine dining, all else similar

---

## Phase 3 — LLM recommendation engine (P2)

**Goal:** Rank the shortlist, write per-restaurant explanations and an optional summary, with a non-LLM fallback.

**Maps to:** problem statement *Integration Layer* (prompt) + *Recommendation Engine*.

### Tasks

1. **Prompt builder** (`src/llm/prompt.py`):
   - System: concierge; rank **only** provided ids; JSON schema; do not invent venues, ratings, or prices; prefer extra-preference fit when ratings are similar; if a preference cannot be verified from fields, say so.
   - User: preferences + compact candidates: `id, name, locality, cuisines, rating, votes, cost_for_two, rest_types, online_order, book_table, dishes_liked, review_excerpt`
   - **Omit** `url`, `phone`, full `address`
   - Ask for `max_results` items
2. **Groq client** (`src/llm/client.py`):
   - Use the official `groq` Python SDK and `GROQ_API_KEY` from `.env`.
   - Read `GROQ_MODEL`, defaulting to `openai/gpt-oss-120b`; supported v1 choices are `openai/gpt-oss-120b` and `qwen/qwen3.8-27b`.
   - Use Groq Structured Outputs (`response_format.type = "json_schema"`, strict schema) for `summary` and recommendation items.
   - Temperature 0.2–0.4; `GROQ_TIMEOUT_SECONDS` default 20; max completion tokens ~800–1200; disable SDK retries so the service owns the single repair attempt and fallback behavior.
3. **Parser** (`src/llm/parser.py`):
   - Parse JSON `{ summary, recommendations: [{ id, rank, explanation }] }`
   - Drop unknown ids; sort by `rank`
   - Join surviving ids to restaurant records
4. **Retry:** one repair call if JSON is invalid; then fallback.
5. **Fallback** (`engine = "fallback"`): top `max_results` by retrieval score; template explanation from rating, cuisine, cost (no model).
6. **Empty candidates:** do not call the LLM; return empty `results`, a user-facing message, `engine` omitted or `"none"`.
7. **Wire** `services/recommend.py`: retrieve → prompt → LLM → parse → `RecommendationResponse` (`summary`, `relaxation_applied`, `engine`: `llm` | `fallback`, `results`).
8. **Logging:** preference hash, candidate count, `retrieval_ms`, `llm_ms`, `engine`. Do not log full review excerpts.

### Exit criteria

- Happy path: 5 cards with names/cuisines/ratings/costs from **data**, explanations from the model
- Kill the API key / force timeout → still 5 heuristic results, `engine = fallback`
- Injected fake id in model output is dropped
- Prompt never contains `phone`
- Either supported `GROQ_MODEL` works without code changes; an unsupported model id fails configuration and uses fallback

### Tests (`tests/test_parser.py`, `tests/test_recommend.py`)

- Mock LLM client (no network in CI)
- Valid JSON join + rank order
- Unknown ids dropped
- Timeout path → fallback template
- Empty retrieval → no client call
- Prompt fixture: no phone/url/address keys
- Groq client fixture: configured model, strict JSON schema, timeout, and token cap are passed to the SDK

---

## Phase 4 — Streamlit UI (P3)

**Goal:** A user-facing demo: preferences in, clear recommendation cards out.

**Maps to:** problem statement *User Input* (collection) + *Output Display*.

### Tasks

1. Load the restaurant store **once** (`st.cache_resource`) from parquet.
2. **Preference panel** bound to facets (not free-typed metros):
   - Locality and/or city-zone dropdowns from store meta
   - Budget: low / medium / high
   - Cuisine multi-select from facet list
   - Min-rating slider
   - Extra preferences text (family-friendly, quick service, …)
   - Submit button (disable double-click / debounce)
3. **States:** idle hint, spinner while recommending, empty (suggest relaxing filters + show `relaxation_applied` if any), error, results.
4. **Results:** summary strip; ranked cards with **name, cuisine, rating, estimated cost (≈ ₹X for two), AI explanation**; optional locality and book-table / online-order badges.
5. **Transparency:** note when `engine = fallback` or search was expanded.
6. Do not render raw `reviews_list` or phone.

### Exit criteria (manual)

Walk through as a user:

| Flow | Expect |
| --- | --- |
| Indiranagar, medium, Italian, min 4.0, “family-friendly” | Summary + 3–5 cards with all required fields |
| Filters that match nothing | Empty state, no crash, no LLM required |
| Missing/invalid LLM key | Cards still appear with fallback note |
| Dropdowns | Only real dataset areas/cuisines |

### Tests

- Optional: extract card DTO mapping and unit-test field presence
- Primary verification is the manual table above

---

## Phase 5 — Polish and optional API (P4)

**Goal:** Sharable project: docs, tests in CI, optional HTTP API.

### Tasks

1. **README:** setup (venv, `pip install`, copy `.env`, run ingest, `streamlit run src/ui/app.py`), dataset credit, Bangalore-only caveat, architecture one-liner (filter then LLM).
2. **FastAPI** (optional, same `services/recommend.py`):
   - `GET /meta` — localities, city_zones, cuisines, budget_bands
   - `POST /recommendations` — request/response as architecture §7
3. **Cache (optional):** in-memory cache keyed by hashed preferences; short TTL.
4. **Tests:** run the Phase 1–3 suite on a fixture store; no HF and no LLM in CI.
5. **Sanity:** parquet in `.gitignore` or documented as generated; secrets only in `.env`.

### Exit criteria

- New clone: README steps produce a working UI after ingest + API key
- `pytest` green without network
- If FastAPI is included: example `GET /meta` and `POST /recommendations` match the architecture JSON

---

## Suggested sequencing on a calendar

Treat as effort, not calendar dates.

| Phase | Focus | Rough effort |
| --- | --- | --- |
| 0 | Skeleton | Small |
| 1 | Ingest + clean + store | Medium (first HF download dominates) |
| 2 | Filters + score + relax | Medium |
| 3 | Prompt + LLM + fallback | Medium |
| 4 | Streamlit | Small–medium |
| 5 | README / tests / API | Small |

**Critical path:** 1 → 2 → 3 → 4. Phase 5 can overlap with 4 (README and tests) except FastAPI, which should wrap the already-stable `recommend()` function.

---

## Definition of done (product)

The app satisfies the problem statement when all of the following are true:

1. User can set location (dataset locality/zone), budget, cuisine, min rating, and extra preferences.
2. Recommendations come from the Hugging Face Zomato data after cleaning.
3. An LLM ranks that shortlist and explains each pick (or fallback copy if the model fails).
4. Each result shows restaurant name, cuisine, rating, estimated cost, and explanation.
5. Eligibility is enforced by code filters, not by trusting the model.

---

## Later (not this plan)

Semantic retrieval over `dish_liked` + review excerpts, then the same hard filters and LLM ranker. API contract stays the same; only the integration layer changes.
