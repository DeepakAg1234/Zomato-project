# Bengaluru Restaurant Finder

A dataset-grounded restaurant recommendation demo. It first filters and scores
restaurants in code, then asks Groq to rank only that shortlist and explain each
result. If the LLM is unavailable, deterministic heuristic recommendations are
returned instead.

> **Dataset scope:** this project is Bangalore/Bengaluru-only. The location
> controls intentionally contain real areas from the dataset, not arbitrary
> Indian cities.

## Data source

Restaurant listings come from the
[Zomato Restaurant Recommendation dataset by Manika Saini](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation)
on Hugging Face. The source data belongs to its respective publisher and is
used here for educational purposes.

## Setup

Python 3.11 or newer is recommended.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Add your Groq API key to `.env`:

```dotenv
GROQ_API_KEY=your-key-here
GROQ_MODEL=openai/gpt-oss-120b
GROQ_TIMEOUT_SECONDS=20
```

The other supported model is `qwen/qwen3.8-27b`.

## Prepare the data

Ingest is a one-time CLI step, not part of an application request:

```bash
python -m src.ingest.load_hf
```

This downloads the Hugging Face dataset, cleans and deduplicates it, and writes
`data/processed/restaurants.parquet` plus `data/processed/facets.json`.
The raw download and generated parquet are intentionally gitignored.

## Run the Streamlit UI

```bash
python -m streamlit run src/ui/app.py
```

Open `http://localhost:8501`. Missing or invalid Groq credentials do not break
the search; the UI labels and displays heuristic fallback results.

## Run the web frontend

The Stitch design lives in `stitch_bengaluru_restaurant_finder_ui_design/` and is
implemented as a component-based React app in `frontend/`. It calls the same
`GET /meta` and `POST /recommendations` API as the Streamlit demo.

Start the API first, then the frontend:

```powershell
python -m uvicorn src.api.app:app --reload
```

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/meta` and `/recommendations` to
the API on port 8000.

`npm run build` writes `frontend/dist`. After that, the API serves the built
UI at `http://localhost:8000/`.

## Run the API

```bash
python -m uvicorn src.api.app:app --reload
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.
Responses are cached in memory by hashed preferences for 60 seconds.

### `GET /meta`

```bash
curl http://localhost:8000/meta
```

Returns dataset-backed `localities`, `city_zones`, `cuisines`, and
`budget_bands`.

### `POST /recommendations`

```bash
curl -X POST http://localhost:8000/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "locality": "Indiranagar",
    "city_zone": null,
    "budget": "medium",
    "cuisines": ["Italian", "Continental"],
    "min_rating": 4.0,
    "extra_preferences": "family-friendly, easy parking",
    "max_results": 5
  }'
```

The response includes the summary, any search relaxation, ranking engine, and
grounded restaurant cards. Use `"any_area": true` when both location fields are
omitted.

## Test

```bash
python -m pytest
```

Tests use an in-memory fixture store and mocked LLM clients. They do not
download the dataset or call Groq, so they are safe to run in CI without
secrets.

## Architecture

`preferences → deterministic filters and scoring → capped shortlist → Groq ranking and explanations → validated restaurant cards`

The LLM never receives the full dataset, phone numbers, URLs, or full
addresses, and returned IDs are joined back to canonical local records.
