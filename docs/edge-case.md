# Edge cases and corner scenarios

Catalog of corner cases for the build in [implementation-plan.md](./implementation-plan.md). Expected behaviour follows [architecture.md](./architecture.md).

**How to use:** each row is a case to handle in code and, where noted, cover with a fixture test. IDs are stable (`P1-R-03`) so tests and tickets can reference them.

**Global invariant:** the LLM never sees the full dataset, never receives phone numbers, and cannot introduce restaurants that were not in the candidate set.

---

## Severity

| Tag | Meaning |
| --- | --- |
| **Must** | Wrong handling breaks eligibility, privacy, or crashes the demo |
| **Should** | Wrong handling yields empty/wrong UX but the app stays up |
| **Nice** | Polish; defer if time-boxed |

---

## Phase 0 — Project skeleton

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P0-01 | Import without `src` on `PYTHONPATH` | Documented run command (`python -m`) works; README if it does not | Should |
| P0-02 | `.env` created from example | File is gitignored; keys never committed | Must |
| P0-03 | Missing optional fields on Pydantic models | Models allow `null` for `rating`, `cost_for_two`, `locality`, `review_excerpt` | Must |
| P0-04 | Windows vs POSIX paths | Ingest/store use `pathlib`; no hardcoded `/` assumptions | Should |

---

## Phase 1 — Ingestion and cleaning

### Dataset load

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-L-01 | Hugging Face unreachable / first download interrupted | CLI fails with a clear error; does not write a half parquet; retry is safe | Must |
| P1-L-02 | Re-run ingest when parquet already exists | Overwrite processed file; no duplicate append | Must |
| P1-L-03 | Run ingest on every Streamlit rerun | **Forbidden.** Ingest is CLI/startup only | Must |
| P1-L-04 | Dataset schema extra/missing columns | Map known columns; skip `menu_item`; fail loudly if `name` / `location` / `cuisines` absent | Must |
| P1-L-05 | Offline after successful cache | Second ingest uses `data/raw/` or HF cache without network | Should |

### Rating parse

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-R-01 | `4.1/5` | `rating = 4.1` | Must |
| P1-R-02 | `NEW` | `rating = null` | Must |
| P1-R-03 | `-` or empty / NaN | `rating = null` | Must |
| P1-R-04 | `3.9 /5` extra spaces | Parse 3.9 | Should |
| P1-R-05 | `4.1 / 5` with spaces around slash | Parse 4.1 | Should |
| P1-R-06 | Bare `4.1` with no `/5` | Parse 4.1 if numeric; else null | Should |
| P1-R-07 | `0` or `5` / `5/5` | Keep 0.0–5.0; do not clip unless >5 or <0 (then null or clamp—pick one and test it) | Should |
| P1-R-08 | Garbage `Rated` / `Opening` | `rating = null`, row kept | Must |

### Cost parse

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-C-01 | `"800"` | `800` | Must |
| P1-C-02 | `"1,200"` | `1200` | Must |
| P1-C-03 | `"1,200.00"` or `"₹1,200"` | Strip currency/commas; int 1200 | Should |
| P1-C-04 | Empty / NaN | `cost_for_two = null`, `budget_band = unknown` | Must |
| P1-C-05 | `"0"` | Treat as null/unknown **or** low—document choice; do not crash | Should |
| P1-C-06 | Non-numeric `"not available"` | null + unknown band | Must |
| P1-C-07 | Boundary `400` | `budget_band = low` | Must |
| P1-C-08 | Boundary `401` | `medium` | Must |
| P1-C-09 | Boundary `1000` | `medium` | Must |
| P1-C-10 | Boundary `1001` | `high` | Must |

### Lists, bools, text

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-T-01 | Cuisines `"Italian, Chinese"` | `["Italian", "Chinese"]`; match later is case-insensitive | Must |
| P1-T-02 | Extra spaces `"Italian,  Chinese,"` | Trim; drop empty tokens | Must |
| P1-T-03 | Null / empty cuisines | `[]`; restaurant can only match if cuisine filter is later relaxed or unused | Must |
| P1-T-04 | `rest_type` same as cuisines (multi, empty) | Same split/trim rules | Must |
| P1-T-05 | `online_order` / `book_table` `Yes`/`No` mixed case | bool | Must |
| P1-T-06 | Unexpected value (`-`, empty) | `false` (or null if you distinguish unknown; then filters must not treat null as Yes) | Should |
| P1-T-07 | `reviews_list` multi-megabyte | Store at most 400 chars in `review_excerpt`; never full blob in parquet-for-prompt | Must |
| P1-T-08 | `reviews_list` empty / `"[]"` | `review_excerpt = null` | Should |
| P1-T-09 | `dish_liked` null | `[]` | Should |
| P1-T-10 | Unicode names (café, non-Latin) | Preserve; UTF-8 parquet | Should |

### Identity and duplicates

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-D-01 | Same `name` + `address`, different `votes` | Keep highest `votes` only | Must |
| P1-D-02 | Same name, different address | Two restaurants, two ids | Must |
| P1-D-03 | Same name+address, equal votes | Keep one (first or max rating); deterministic | Should |
| P1-D-04 | Missing address | Hash still stable (e.g. name + empty); do not collide unrelated rows if possible | Should |
| P1-D-05 | Re-ingest | Same name+address → same `id` | Must |

### Facets and product geography

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P1-F-01 | User expects “Delhi” as location | Delhi is **not** in facets unless present in data; UI must not offer invented metros | Must |
| P1-F-02 | Duplicate facet strings differing by case/space | Normalize for matching; display one canonical label | Should |
| P1-F-03 | Thousands of cuisine strings | Facets frequency-sorted; UI can show top N + search, still match on full list | Should |
| P1-F-04 | Phone column present in raw data | Not copied onto prompt-facing `Restaurant`; optional omit from parquet | Must |

---

## Phase 2 — Preferences, filters, scoring

### Validation

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P2-V-01 | `budget` not in `{low, medium, high}` | 422 / validation error; no retrieval | Must |
| P2-V-02 | `min_rating` `< 0` or `> 5` | Reject | Must |
| P2-V-03 | `min_rating` `3.5` vs `3.50` | Same filter | Nice |
| P2-V-04 | `extra_preferences` > ~300 chars | Reject or truncate with warning; bound prompt size | Must |
| P2-V-05 | `extra_preferences` empty | Allowed; heuristic component = 0 | Must |
| P2-V-06 | `max_results` omitted | Default 5 | Must |
| P2-V-07 | `max_results` `0` or negative | Reject | Must |
| P2-V-08 | `max_results` `11` or `999` | Cap at 10 (or reject) | Must |
| P2-V-09 | Neither `locality` nor `city_zone` | Only if explicit “any area”; otherwise reject or warn that results are city-wide | Should |
| P2-V-10 | Both locality and city_zone set and they disagree | Document: prefer locality **or** AND both; tests lock the choice | Must |
| P2-V-11 | `cuisines: []` | Treat as no cuisine constraint **or** reject; lock in tests | Must |
| P2-V-12 | Unknown locality string not in facets (API caller) | Empty candidates or 400; do not fuzzy-match to a random area | Should |

### Hard filters

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P2-H-01 | Locality match, city_zone ignored | Only that locality | Must |
| P2-H-02 | City_zone only | All localities in that zone | Must |
| P2-H-03 | Cuisine `"italian"` vs data `"Italian"` | Match | Must |
| P2-H-04 | Request `["Italian", "Chinese"]` | OR: any overlap (not require both) unless you document AND | Must |
| P2-H-05 | Restaurant cuisines empty | Fail cuisine filter when cuisines requested | Must |
| P2-H-06 | `min_rating = 4.0`, restaurant `3.9` | Exclude | Must |
| P2-H-07 | `min_rating = 4.0`, restaurant `4.0` | Include | Must |
| P2-H-08 | `min_rating` set, `rating` null | **Exclude** | Must |
| P2-H-09 | `min_rating = 0`, null ratings | Define: still drop nulls **or** include; default **drop nulls** if any min is applied | Should |
| P2-H-10 | Budget `medium`, restaurant `unknown` cost | Exclude on first pass; may enter on relaxation (see P2-X) | Must |
| P2-H-11 | All four filters together | Intersection only | Must |
| P2-H-12 | Zero matches after all filters + all relaxations | Empty list; do not invent rows | Must |

### Relaxation (count **< 3**)

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P2-X-01 | Exactly 3 matches | **No** relaxation | Must |
| P2-X-02 | Exactly 2 matches | Relaxation starts; `relaxation_applied` set | Must |
| P2-X-03 | 0 matches | Apply steps in order until ≥3 or steps exhausted | Must |
| P2-X-04 | Step 1: locality set | Expand to that row’s / mapping’s `city_zone` | Must |
| P2-X-05 | Step 1: only city_zone was set | Skip locality expand | Should |
| P2-X-06 | Step 2: neighbouring budget | low↔medium, medium↔low and high, high↔medium; include `unknown` if still short | Must |
| P2-X-07 | Step 3: drop cuisine | Keep area + rating (+ possibly expanded budget) | Must |
| P2-X-08 | After step 3 still < 3 | Return whatever remains (0–2); UI empty/partial; **do not** drop min_rating in v1 | Must |
| P2-X-09 | Relaxation used | Response records which step(s); UI can explain expansion | Must |
| P2-X-10 | Relaxation would include a restaurant failing min_rating | Still excluded | Must |

### Scoring and K cap

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P2-S-01 | All ratings null in the scored set | `norm(rating)` = 0; do not divide by zero | Must |
| P2-S-02 | All votes 0 | `log1p(0)` fine; no NaN | Must |
| P2-S-03 | Single candidate | Score defined; K = 1 | Must |
| P2-S-04 | Cuisine overlap 0 vs 1 vs 2 of 2 requested | Higher overlap scores higher | Should |
| P2-S-05 | Extra text `"quick service"` / `"fast"` | Boost Quick Bites / Delivery / Cafe vs Casual Dining, all else similar | Must |
| P2-S-06 | `"family-friendly"` | Boost Casual Dining / Buffet / book_table | Should |
| P2-S-07 | `"date"` / `"romantic"` | Boost book_table / desserts / high rating | Should |
| P2-S-08 | Extra text with no keyword | Heuristic 0; no crash | Must |
| P2-S-09 | Injection-like extra text (`ignore instructions`) | Treated as keywords only; **does not** change filters | Must |
| P2-S-10 | >15 pass filters | Return only top K (8–15, default 12), stable tie-break (e.g. id) | Must |
| P2-S-11 | Same preferences twice | Same candidate ids in same order | Must |
| P2-S-12 | Ties in score | Deterministic secondary key | Must |
| P2-S-13 | Phone on candidate DTO | Absent | Must |

---

## Phase 3 — LLM engine

### Prompt

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P3-P-01 | Candidate has `url`, `address`, `phone` in store | Prompt JSON/text omits them | Must |
| P3-P-02 | `review_excerpt` present | At most 400 chars in prompt | Must |
| P3-P-03 | K = 12, `max_results` = 5 | Prompt still includes K; ask for 5 in the output | Must |
| P3-P-04 | Extra preferences unverifiable (“easy parking”) | System tells model to say so honestly, not invent | Should |
| P3-P-05 | Empty candidate list | **No LLM call** | Must |

### Model / HTTP failures

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P3-F-01 | Missing / invalid API key | Fallback list; `engine = fallback` | Must |
| P3-F-02 | Timeout (> ~20s) | Fallback; no hang in UI | Must |
| P3-F-03 | Provider 429 / 5xx | Fallback (retry-once optional; then fallback) | Must |
| P3-F-04 | Network DNS failure | Fallback | Must |
| P3-F-05 | Empty model body | Repair once, then fallback | Must |

### Parser and grounding

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P3-J-01 | Valid JSON, all ids in candidate set | Join; sort by `rank`; `engine = llm` | Must |
| P3-J-02 | Markdown fences ` ```json ` | Strip; parse | Should |
| P3-J-03 | Trailing commentary after JSON | Extract first JSON object if possible; else repair/fallback | Should |
| P3-J-04 | Invalid JSON | One repair call; then fallback | Must |
| P3-J-05 | Unknown `id` (hallucinated venue) | Drop that item; never create a restaurant | Must |
| P3-J-06 | Duplicate ids | Keep first by rank; one card | Should |
| P3-J-07 | Missing `rank` | Use array order | Should |
| P3-J-08 | Conflicting ranks (two `1`s) | Stable sort; unique display rank 1..n after join | Should |
| P3-J-09 | More items than `max_results` | Truncate to `max_results` | Must |
| P3-J-10 | Fewer items than `max_results` but more candidates | Return what the model sent **or** backfill from score; prefer backfill with fallback explanations so the user still sees N cards | Should |
| P3-J-11 | All ids unknown | Fallback entire list | Must |
| P3-J-12 | Model invents rating/price in explanation | Display **store** rating/cost on the card; explanation is copy only | Must |
| P3-J-13 | Explanation empty | Template fallback for that row | Should |
| P3-J-14 | `summary` missing | UI works without summary strip | Should |
| P3-J-15 | Extremely long explanation | Truncate for UI (~400 chars) | Nice |

### Fallback and empty

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P3-B-01 | Fallback explanations | Template from rating, cuisine, cost; not blank | Must |
| P3-B-02 | Fallback count | `max_results` or all candidates if fewer | Must |
| P3-B-03 | Zero candidates | `results = []`, message, `engine` `none` or omitted; **zero** LLM calls | Must |
| P3-B-04 | Logging | Hash prefs, counts, timings, engine; **no** full excerpts / prompts with reviews | Must |

---

## Phase 4 — Streamlit UI

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P4-01 | First load, parquet missing | Error: run ingest; no stack trace wall | Must |
| P4-02 | Corrupt / partial parquet | Clear load error | Must |
| P4-03 | Streamlit rerun on widget change | Store loaded via `st.cache_resource`; no HF download | Must |
| P4-04 | Double-click Submit | One in-flight request (debounce/disable) | Should |
| P4-05 | Empty cuisine selection | Same as P2-V-11; form should not crash | Must |
| P4-06 | No area selected | Validation message; no call or explicit any-area | Should |
| P4-07 | Zero results | Empty state + suggest looser filters; show `relaxation_applied` if set | Must |
| P4-08 | `engine = fallback` | Visible note; cards still complete | Must |
| P4-09 | `relaxation_applied` set | Visible “we expanded your search” | Must |
| P4-10 | Missing cost on a card | Show “Cost unknown”, not `₹None` | Must |
| P4-11 | Missing rating | Show “Unrated” / “NEW”; do not render `None/5` | Must |
| P4-12 | Many cuisines on one row | Truncate with +N; full list on expand/tooltip | Nice |
| P4-13 | Long restaurant name | Wrap; does not break layout | Should |
| P4-14 | `url` present | Optional link; not required | Nice |
| P4-15 | Phone / raw reviews | **Never** shown | Must |
| P4-16 | LLM still running | Spinner; no duplicate submits | Should |
| P4-17 | Unhandled exception in recommend | Error state, app remains usable | Must |
| P4-18 | Dropdown values | Only facet localities/cuisines (Bangalore areas) | Must |
| P4-19 | Idle (never submitted) | Hint, not a fake result list | Should |
| P4-20 | Session: change filters after results | New submit replaces old cards; no mixed ranks | Should |

---

## Phase 5 — API, cache, CI, secrets

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| P5-01 | `GET /meta` before ingest | 503 + “run ingest”, not empty 200 that looks like “no restaurants exist” | Should |
| P5-02 | `POST /recommendations` extra fields | Ignore or 422; do not crash | Should |
| P5-03 | `POST` wrong types (`min_rating: "high"`) | 422 | Must |
| P5-04 | Oversized JSON body | Reject; protect prompt/DoS | Should |
| P5-05 | Cache hit after fallback vs later LLM success | Cache key includes engine **or** short TTL; do not permanently cache fallback as success | Should |
| P5-06 | Cache key | Hash of canonical preferences (sorted cuisines); not raw JSON key order | Should |
| P5-07 | pytest with no network | Green; mocked LLM; fixture ~20 rows; no HF | Must |
| P5-08 | README clone missing API key | UI still runs via fallback; documented | Should |
| P5-09 | Parquet committed by mistake | Prefer gitignore generated data; document size | Should |
| P5-10 | Concurrent API requests | Stateless recommend + read-only store; no shared mutable prompt buffer | Must |

---

## Cross-cutting (any phase)

| ID | Scenario | Expected | Severity |
| --- | --- | --- | --- |
| X-01 | LLM returns a restaurant not in the filtered set | Dropped (same as unknown id) | Must |
| X-02 | User asks for Delhi / Mumbai in extra text only | Filters still use dropdown area; model may mention the mismatch honestly | Should |
| X-03 | Prompt injection in extra_preferences | Filters/score/candidates unchanged; model output still id-constrained | Must |
| X-04 | PII: phone in raw dataset | Never in prompt, logs, or UI | Must |
| X-05 | Cost/latency: 51k rows to the model | **Forbidden** | Must |
| X-06 | Non-ASCII extra_preferences | Allowed within length cap | Should |

---

## Fixture matrix (minimum tests)

Use the ~20-row fixture from the implementation plan. Prioritise **Must** rows.

| Fixture idea | Covers |
| --- | --- |
| Rate `NEW`, `-`, `4.1/5` | P1-R-01–03, P2-H-08 |
| Cost `1,200`, empty, 400/401/1000/1001 | P1-C-02, 04, 07–10 |
| Dup name+address, different votes | P1-D-01 |
| Italian vs italian; empty cuisines | P2-H-03, P2-H-05 |
| 2 matches → relaxation; 3 matches → none | P2-X-01, P2-X-02 |
| Mock LLM unknown id + timeout | P3-J-05, P3-F-02 |
| Empty retrieval | P3-P-05, P3-B-03 |
| Prompt snapshot has no `phone` | P3-P-01, P1-F-04 |

---

## Out of scope (do not treat as v1 bugs)

- Live availability, menu, or booking failures
- Users in cities not in the Hugging Face file
- Embedding/vector miss rates
- Account / auth edge cases
- Provider billing limits beyond 429 → fallback
