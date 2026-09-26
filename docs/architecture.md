# Architecture

## AI-Powered Restaurant Recommendation System (Zomato Use Case)

This document defines how the product in [problemStatement.md](./problemStatement.md) is built: components, data flow, filtering, LLM integration, APIs, and delivery.

**North star:** structured restaurant data does the hard filtering; the LLM only ranks a small candidate set and writes human-like explanations. Never send the full dataset to the model.

---

## 1. Goals and constraints

### Functional goals

| Goal | How architecture supports it |
| --- | --- |
| Capture location, budget, cuisine, min rating, extra preferences | Typed preference schema on the API and UI |
| Use a real Zomato dataset | One-time ingest from Hugging Face, then local processed store |
| Personalized, human-like recommendations | LLM ranks filtered candidates and returns explanations |
| Clear results | Normalized recommendation DTO rendered as cards |

### Non-functional constraints

- **Cost / latency:** LLM is called once per request on ≤15 candidates, not 51k rows.
- **Determinism of eligibility:** hard filters (city/area, budget, cuisine, rating) are code, not the model.
- **Graceful degradation:** if the LLM fails, return the filtered/ranked-by-score list with a fallback explanation.
- **No secrets in the client:** API keys live only on the server.

---

## 2. High-level architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Presentation                             │
│  Web UI: preference form → recommendation cards + summary        │
└──────────────────────────────┬──────────────────────────────────┘
                               │ HTTPS JSON
┌──────────────────────────────▼──────────────────────────────────┐
│                         API layer                                │
│  POST /recommendations  ·  GET /meta (locations, cuisines)       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌────────────────────┐
│ Preference    │    │ Candidate       │    │ Recommendation     │
│ validation    │───▶│ retrieval       │───▶│ engine (LLM)       │
│               │    │ (filter + score)│    │ rank + explain     │
└───────────────┘    └────────┬────────┘    └─────────┬──────────┘
                              │                       │
                              ▼                       ▼
                     ┌─────────────────┐    ┌────────────────────┐
                     │ Restaurant      │    │ LLM provider       │
                     │ store (parquet/ │    │ (Groq)             │
                     │ SQLite)         │    └────────────────────┘
                     └────────┬────────┘
                              ▲
                     ┌────────┴────────┐
                     │ Ingest pipeline │
                     │ Hugging Face →  │
                     │ clean → store   │
                     └─────────────────┘
```

**Pattern:** retrieve-then-generate. The integration layer is a deterministic retriever; the recommendation engine is a generative ranker.

---

## 3. Recommended tech stack

| Layer | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | Native fit for `datasets`, pandas, LLM SDKs |
| API | FastAPI | Typed request/response, easy OpenAPI |
| UI (MVP) | Streamlit | Fast form + cards; enough for the use case |
| UI (product-like, optional) | Next.js calling the same API | Richer UX without changing the backend |
| Data ingest | Hugging Face `datasets` | Official source: [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation) |
| Processed store | Parquet + in-memory pandas **or** SQLite | ~52k rows; pandas is enough; SQLite if you want SQL filters |
| LLM | Groq (`openai/gpt-oss-120b` or `qwen/qwen3.8-27b`) | Fast inference with strict JSON Schema output |
| Config | `.env` (`GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_TIMEOUT_SECONDS`) | Select either supported Groq model without code changes |

**MVP delivery:** one Python app (Streamlit + shared service layer). Split FastAPI later if a separate frontend is needed; keep retrieval and prompt building in a `services/` package so both UIs share logic.

Suggested layout:

```
restaurant-finder/
  docs/
    problemStatement.md
    architecture.md
  data/
    raw/                 # optional cache of HF download
    processed/
      restaurants.parquet
  src/
    ingest/
      load_hf.py
      clean.py
    store/
      restaurant_store.py
    retrieval/
      filters.py
      scorer.py
    llm/
      prompt.py
      client.py
      parser.py
    services/
      recommend.py
    api/
      app.py             # FastAPI (optional for MVP)
    ui/
      app.py             # Streamlit
  tests/
  .env.example
  requirements.txt
```

---

## 4. Dataset and canonical restaurant model

### 4.1 Source

- **Dataset:** `ManikaSaini/zomato-restaurant-recommendation`
- **Scale:** ~51.7k rows, `train` split only
- **Important product note:** listings are **Bangalore-centric** (areas / `listed_in(city)` such as Koramangala, Indiranagar, Whitefield). The problem statement examples include “Delhi, Bangalore”; the **filter must use actual dataset areas**, not Indian metro names unless they appear in the data. Surface real locations in the UI dropdown so users cannot request cities that return zero rows.

### 4.2 Raw fields (ingest)

| Raw column | Role |
| --- | --- |
| `name` | Restaurant name |
| `location` | Neighbourhood / locality |
| `listed_in(city)` | Broader listing city/zone |
| `cuisines` | Comma-separated cuisine list |
| `approx_cost(for two people)` | Cost for two (string, often with commas) |
| `rate` | e.g. `4.1/5`, `NEW`, `-` |
| `votes` | Review volume (ranking signal) |
| `rest_type` | Casual Dining, Café, Quick Bites, … |
| `online_order`, `book_table` | Yes/No capabilities |
| `dish_liked` | Soft preference matching |
| `reviews_list` | Optional snippets for LLM context (truncate) |
| `listed_in(type)` | Delivery, Dine-out, Cafes, Buffet, … |
| `address`, `url`, `phone` | Display / deep link |
| `menu_item` | Usually skip (noisy, large) |

### 4.3 Canonical record (after cleaning)

Every row becomes a `Restaurant` used by retrieval and prompts:

```text
Restaurant
  id                hash(name + address) or row index
  name              string
  locality          location
  city_zone         listed_in(city)
  address           string
  cuisines          list[string]
  rest_types        list[string]
  listing_type      string
  cost_for_two      int | null
  budget_band       low | medium | high | unknown
  rating            float | null          # parsed from rate
  votes             int
  online_order      bool
  book_table        bool
  dishes_liked      list[string]
  review_excerpt    string | null         # first N chars of reviews_list
  url               string | null
```

### 4.4 Cleaning rules

| Issue | Rule |
| --- | --- |
| `rate` = `NEW`, `-`, empty | `rating = null` (exclude from min-rating filter unless user allows unrated) |
| `rate` = `4.1/5` | parse `4.1` |
| cost `"1,200"` / `"800"` | strip commas → int |
| missing cost | `cost_for_two = null`, `budget_band = unknown` |
| cuisines / rest_type | split on `,`, trim, lowercase for matching, keep display casing |
| duplicate name+address | keep highest `votes` row |
| `reviews_list` | never store full blob in the prompt; keep ≤400 characters |

**Budget bands** (cost for two; tune after looking at percentiles, starting defaults):

| Band | Cost for two (INR) |
| --- | --- |
| low | ≤ 400 |
| medium | 401–1000 |
| high | > 1000 |

---

## 5. Component design

### 5.1 Data ingestion

**When:** build/startup or a CLI (`python -m src.ingest.load_hf`). Not on every user request.

**Steps:**

1. `load_dataset("ManikaSaini/zomato-restaurant-recommendation", split="train")`
2. Map columns → canonical schema
3. Apply cleaning rules
4. Write `data/processed/restaurants.parquet`
5. Build **facet lists** for the UI: unique localities, city zones, cuisines (top N + search)

Idempotent: re-running ingest overwrites processed files.

### 5.2 Restaurant store

- Load parquet once into memory at process start (52k rows is small).
- Indexes (pandas or dicts):
  - by `city_zone`, `locality`
  - cuisine membership (exploded cuisine → row ids)
- `GET /meta` reads these facets so dropdowns stay aligned with data.

### 5.3 User input (preference schema)

```text
UserPreferences
  locality          string | null     # maps to location
  city_zone         string | null     # maps to listed_in(city)
  budget            low | medium | high
  cuisines          list[string]      # at least one preferred, OR match
  min_rating        float             # e.g. 3.5–4.5
  extra_preferences string            # free text: "family-friendly, quick service"
  max_results       int               # default 5, max 10
```

**Validation:**

- At least one of `locality` or `city_zone` should be set (or allow “any area” with a warning that results are broader).
- `min_rating` in `[0, 5]`
- `extra_preferences` max length (~300 chars) to bound prompt size

### 5.4 Integration layer (candidate retrieval)

This is the **only** place that touches the full dataset.

**Hard filters (must pass):**

1. Area: `locality == preference.locality` OR `city_zone == preference.city_zone`
2. Budget: `budget_band == preference.budget` (optionally include `unknown` if the candidate set is too small)
3. Cuisine: intersection of restaurant cuisines with requested list (case-insensitive)
4. Rating: `rating >= min_rating` (drop null ratings when min_rating is set)

**Soft score (pre-LLM ranking, used to pick top K):**

```text
score =
  0.45 * normalize(rating) +
  0.25 * log1p(votes) normalized +
  0.20 * cuisine_overlap_ratio +
  0.10 * extra_preference_heuristic
```

`extra_preference_heuristic` is cheap keyword matching against `rest_types`, `listing_type`, `dishes_liked`, `online_order`, `book_table`:

| User phrase (examples) | Signals |
| --- | --- |
| family-friendly | Casual Dining, Buffet, high cost_for_two, book_table |
| quick service / fast | Quick Bites, Delivery, Cafe |
| date / romantic | book_table, Desserts, high rating |
| outdoor / cafe | Cafe, rest_type contains Café |

If hard filters yield **< 3** restaurants, relax in order: (1) include adjacent `city_zone` if locality was set, (2) include neighbouring budget band, (3) drop cuisine to “any” but keep area + rating. Record which relaxation was used so the UI can say “We expanded your search because few places matched.”

**Candidate cap:** take top **K = 8–15** by `score`. That set is what the LLM sees.

### 5.5 Recommendation engine (LLM)

**Responsibilities:**

- Rank the K candidates for *this* user
- Write a short explanation per restaurant
- Optionally produce a 1–2 sentence overall summary
- **Must not invent** restaurants, ratings, or prices. IDs in the prompt are the only allowed outputs.

**Prompt structure (system + user):**

1. **System:** You are a restaurant concierge. Rank only the provided candidates. Return JSON matching the schema. Do not invent venues. Prefer better fit to extra preferences when ratings are similar.
2. **User:** serialized preferences + compact candidate list:

```text
id, name, locality, cuisines, rating, votes, cost_for_two, rest_types,
online_order, book_table, dishes_liked, review_excerpt
```

**Output schema (strict JSON):**

```json
{
  "summary": "string",
  "recommendations": [
    {
      "id": "string",
      "rank": 1,
      "explanation": "string"
    }
  ]
}
```

Return `max_results` items (default 5). Parser maps `id` back to the canonical restaurant; drop unknown ids.

**Model settings:** temperature `0.2–0.4`, JSON mode / schema if the provider supports it, max tokens sized for 5 explanations (~800–1200).

**Failure modes:**

| Failure | Behavior |
| --- | --- |
| Timeout / 5xx | Fallback: top `max_results` by retrieval `score`; explanation = template from rating, cuisine, cost |
| Invalid JSON / unknown ids | Retry once with a “fix JSON” instruction; then fallback |
| Empty candidates | HTTP 200 with empty list + message: no matches; suggest relaxing filters |

### 5.6 Output display

Each card binds API fields:

| UI | Source |
| --- | --- |
| Restaurant name | `name` |
| Cuisine | joined `cuisines` |
| Rating | `rating` (+ votes) |
| Estimated cost | `cost_for_two` (show as “≈ ₹X for two”) |
| AI explanation | LLM `explanation` or fallback text |
| Optional extras | locality, rest_type, book_table / online_order badges |
| Summary strip | LLM `summary` |

Do not show raw `reviews_list` blobs.

---

## 6. Request lifecycle

```text
1. User submits preferences in the UI
2. API validates UserPreferences
3. Store query → hard filter → score → top K candidates
4. If K == 0 → return empty result + relaxation hint
5. Prompt builder serializes preferences + candidates
6. LLM client calls provider (timeout ~20s)
7. Parser validates ids ⊂ candidate ids, sorts by rank
8. Join LLM output with restaurant records → RecommendationResponse
9. UI renders summary + ranked cards
```

Sequence:

```text
UI → API → Retriever → Store
              │
              ▼
           PromptBuilder → LLM Provider
              │
              ▼
           Parser → API → UI
```

---

## 7. API contracts

### `GET /meta`

Facets for forms.

```json
{
  "localities": ["Indiranagar", "Koramangala 5th Block"],
  "city_zones": ["BTM", "Koramangala"],
  "cuisines": ["North Indian", "Chinese", "Italian"],
  "budget_bands": ["low", "medium", "high"]
}
```

### `POST /recommendations`

**Request**

```json
{
  "locality": "Indiranagar",
  "city_zone": null,
  "budget": "medium",
  "cuisines": ["Italian", "Continental"],
  "min_rating": 4.0,
  "extra_preferences": "family-friendly, easy parking",
  "max_results": 5
}
```

**Response**

```json
{
  "summary": "These Indiranagar spots fit a medium budget and Italian/Continental with strong ratings.",
  "relaxation_applied": null,
  "engine": "llm",
  "results": [
    {
      "rank": 1,
      "name": "Example Trattoria",
      "cuisines": ["Italian", "Pizza"],
      "rating": 4.3,
      "votes": 1204,
      "cost_for_two": 800,
      "locality": "Indiranagar",
      "explanation": "…",
      "url": "https://…"
    }
  ]
}
```

`engine` is `"llm"` or `"fallback"` so the UI can label AI vs heuristic copy.

---

## 8. Prompt design principles

- **Grounding:** candidates are the closed world. Instruct: “If extra preferences cannot be verified from the fields, say so honestly.”
- **Explanations:** 1–2 sentences, cite concrete fields (rating, cost, cuisine, rest type), not generic praise.
- **Ranking instruction:** fit to extra preferences first, then rating/votes, then cost alignment with budget.
- **Token budget:** omit `url`, `phone`, full address from the prompt; keep `review_excerpt` short.

---

## 9. UI structure

1. **Header** — product name + one-line value (“Find a restaurant that fits you, with reasons”)
2. **Preference panel** — locality/zone dropdowns from `/meta`, budget segmented control, cuisine multi-select, min-rating slider, extra-preferences text box, submit
3. **States** — idle, loading, empty (with relaxation CTA), error, results
4. **Results** — summary, then ranked cards (name, cuisine, rating, cost, explanation)
5. **Transparency** — if `relaxation_applied` or `engine = fallback`, show a short note

Streamlit maps 1:1 to this. A later Next.js UI should consume the same JSON.

---

## 10. Configuration, security, and operations

| Concern | Approach |
| --- | --- |
| Secrets | `GROQ_API_KEY` in environment; never commit `.env` |
| Rate limits | Debounce UI submit; optional in-memory cache keyed by hashed preferences |
| PII | Dataset has phone numbers — **do not send phone to the LLM**; optional to hide in UI |
| Logging | Log preference hash, candidate count, latency, engine used — not full prompts if they contain reviews |
| Observability | Timers: retrieval_ms, llm_ms, total_ms |
| Caching ingest | Persist parquet so demos work offline after first download |

---

## 11. Testing strategy

| Layer | What to test |
| --- | --- |
| Cleaning | `rate` / cost parsers, cuisine split, duplicate collapse |
| Filters | locality + budget + cuisine + min_rating combinations; empty set |
| Relaxation | triggers only below threshold; recorded on the response |
| Prompt | candidate payload size; no disallowed fields |
| Parser | valid JSON, dropped unknown ids, rank order |
| Fallback | LLM timeout still returns 5 scored rows |
| Contract | sample `POST /recommendations` snapshot |

Use a **fixture of ~20 restaurants** for unit tests; do not hit Hugging Face or the LLM in CI. Mock the LLM client.

---

## 12. Build phases

| Phase | Scope | Outcome |
| --- | --- | --- |
| **P0 Ingest** | HF load, clean, parquet, facet lists | Inspectable restaurant table |
| **P1 Retrieval** | Preference filters + scoring + K candidates | Deterministic shortlist without LLM |
| **P2 LLM** | Prompt, JSON parse, explanations, fallback | Full recommendation engine |
| **P3 UI** | Form + cards + empty/error/fallback states | Demo-ready app |
| **P4 Polish** | FastAPI split (optional), cache, tests, README | Sharable project |

P1 is already a useful product (filter + sort). P2 is what makes it “AI-powered” per the problem statement.

---

## 13. Out of scope (v1)

- Live Zomato API, bookings, or payments
- User accounts, history, or collaborative filtering
- Fine-tuning or embeddings over all reviews (optional later: vector search on `dish_liked` + reviews)
- Multi-city coverage beyond what the Hugging Face file contains
- Real-time menus or availability

**Later extension:** embed `dish_liked` + review excerpts, retrieve by semantic match to `extra_preferences`, then still apply hard filters and LLM ranking. That upgrades the integration layer without changing the API contract.

---

## 14. Decision summary

| Decision | Choice |
| --- | --- |
| Architecture style | Filter/retrieve, then LLM rank-and-explain |
| Source of truth for eligibility | Code filters on cleaned tabular data |
| LLM role | Ranker + copywriter on a closed candidate set |
| Data source | Hugging Face Zomato set, processed to parquet |
| Primary runtime | Python; Streamlit MVP, FastAPI-ready services |
| Failure default | Heuristic top-N with templated reasons |

This satisfies the problem statement workflow: **ingest → user input → integration layer → recommendation engine → output display**, with a clear boundary so the model cannot invent restaurants or ignore budget, cuisine, rating, or location.
