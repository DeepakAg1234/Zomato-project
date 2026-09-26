# Deployment Plan

Deploy the Bengaluru Restaurant Finder as two services: the React frontend on **Vercel**, and the FastAPI API on **Railway**.

**Sources:** [architecture.md](./architecture.md) · [README.md](../README.md)

**What ships:** the latest web UI in `frontend/` (Vite + React) and the recommendation API in `src/api/app.py`. Streamlit (`src/ui/app.py`) stays a local demo and is not deployed.

---

## 1. Target topology

```
Browser
   │
   │  HTTPS (static assets)
   ▼
Vercel  ──  frontend/  (Vite build → dist)
   │
   │  HTTPS JSON
   │  GET  /meta
   │  POST /recommendations
   ▼
Railway ──  FastAPI (uvicorn)
   │           ├── data/processed/restaurants.parquet  (baked into the image)
   │           ├── data/processed/facets.json
   │           └── Groq API  (GROQ_API_KEY stays on Railway only)
   ▼
Groq
```

| Piece | Host | Why |
| --- | --- | --- |
| `frontend/` | Vercel | Static Vite build. No server, no secrets. |
| `src/api` + processed data | Railway | Long-lived Python process. Holds the ~52k-row dataframe in memory and waits on Groq (up to `GROQ_TIMEOUT_SECONDS`). |
| Streamlit | Not deployed | Same service layer, local only. |

The API is not a Vercel serverless function. A recommendation can take the full Groq timeout, and the process must keep the parquet store resident. Railway is the right runtime for that.

Locally, Vite proxies `/meta` and `/recommendations` to `http://127.0.0.1:8000`, and FastAPI can also serve `frontend/dist` from `/`. In production those two shortcuts go away: the browser talks to Vercel, and Vercel’s built JS talks to Railway.

---

## 2. Gaps that block a deploy today

These are facts about the current repo. Fix them before the first production deploy.

| Gap | Where | What production needs |
| --- | --- | --- |
| CORS allows only localhost | `src/api/app.py` (`_LOCAL_UI_ORIGINS`) | The Vercel production origin, and preview origins, or the browser will block every call. |
| `VITE_API_BASE` defaults to `""` | `frontend/src/api.ts` | On Vercel, set it to the Railway public URL. Vite inlines this at **build** time. |
| Parquet is gitignored | `.gitignore` (`*.parquet`) | Railway clones git, so the image has no catalogue unless ingest runs during the image build. `facets.json` is tracked; the parquet is not. |
| No container or start config | repo root | Railway needs a Dockerfile (or an explicit start command) that binds `0.0.0.0:$PORT`. |
| No lightweight health route | `src/api/app.py` | `/meta` loads the full store. A `/health` route that does not touch parquet lets Railway’s healthcheck pass before the first real request. |
| Full `requirements.txt` | repo root | Includes Streamlit, pytest, and Hugging Face `datasets`. The API image should install a slimmer file, and install `datasets` only for the build step that runs ingest. |

`python-dotenv` already calls `load_dotenv()` inside `GroqLLMClient.from_env()`. Railway-injected variables are enough; do not commit or upload `.env`.

---

## 3. Code and config to add first

Do this on a branch, then deploy. Order matters: the API must accept the Vercel origin before the frontend build points at it.

### 3.1 CORS from the environment

Keep the four localhost origins for local `npm run dev`. Add origins from `CORS_ORIGINS` (comma-separated, no spaces required).

Example value on Railway:

```text
CORS_ORIGINS=https://<project>.vercel.app,https://<custom-domain>
```

Preview deployments use a different host every time (`<project>-git-<branch>-<team>.vercel.app`). Either:

- set `CORS_ORIGIN_REGEX` to something like `https://<project>.*\.vercel\.app`, or
- turn off Vercel preview protection and add each preview URL by hand.

Allow methods `GET` and `POST`, and header `Content-Type`. Do not set `allow_credentials` unless the browser starts sending cookies. The current UI does not.

### 3.2 `GET /health`

Return `{"status": "ok"}` without calling `RestaurantStore.load()`. Railway’s healthcheck should hit `/health`. The first user request (or an explicit startup hook) still loads the store and returns 503 from `/meta` if the parquet is missing.

### 3.3 API-only requirements

Add `requirements-api.txt` used by the running container:

- keep: `pandas`, `pyarrow`, `python-dotenv`, `pydantic`, `groq`, `fastapi`, `uvicorn`
- drop: `streamlit`, `pytest`, `datasets`

`datasets` is only needed to run `python -m src.ingest.load_hf`. Install it in the Docker build stage that performs ingest, not in the final runtime layer if the parquet is already written.

### 3.4 Dockerfile

Build from the repo root. Pin Python **3.13** to match `.github/workflows/tests.yml`.

```dockerfile
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY data/processed/facets.json data/processed/facets.json
RUN python -m src.ingest.load_hf

FROM python:3.13-slim
WORKDIR /app
COPY requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src ./src
COPY --from=build /app/data/processed ./data/processed
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Notes:

- One worker. The store and the 60-second recommendation cache are process-local. Extra workers multiply RAM and split the cache.
- Do not copy `frontend/dist` into this image. `_mount_frontend` then no-ops, which is what we want when Vercel owns the UI.
- Ingest during **image build**, not on container start. A start-time download of the Hugging Face dataset can exceed Railway’s healthcheck window, and the container disk is wiped on every redeploy unless a volume is attached.
- The build stage needs outbound network access to Hugging Face.

### 3.5 Railway config

`railway.toml` at the repo root:

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 120
restartPolicyType = "ON_FAILURE"
```

`healthcheckTimeout` of 120 seconds covers loading pandas and the parquet on first boot. It does not cover a fresh Hugging Face download.

### 3.6 Vercel config

No rewrite file is required. The UI is a single page with no client router.

In the Vercel project:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Environment variable | `VITE_API_BASE` = Railway public URL, no trailing slash |

`npm run build` runs `tsc --noEmit` and then `vite build`. A type error fails the Vercel build. That is intended.

---

## 4. Data

| File | In git | In the Railway image |
| --- | --- | --- |
| `data/processed/facets.json` | Yes | Yes (also regenerated by ingest) |
| `data/processed/restaurants.parquet` | No (`*.parquet`) | Yes, produced by `python -m src.ingest.load_hf` in the build stage |
| `data/raw/` | No | No. Build cache only; do not copy it into the runtime image. |

The catalogue refreshes only when the Railway image is rebuilt. That matches the product: ingest is a one-time pipeline, not a request path.

Memory: the store loads the full frame into pandas on first `/meta` or `/recommendations` call. Size the Railway service at **1 GB RAM**. 512 MB is tight once pandas, pyarrow, and the frame are resident.

---

## 5. Environment variables

### Railway (API)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `GROQ_API_KEY` | Yes | `gsk_…` | Server only. Never set this on Vercel. |
| `GROQ_MODEL` | No | `openai/gpt-oss-120b` | Other supported value: `qwen/qwen3.8-27b`. |
| `GROQ_TIMEOUT_SECONDS` | No | `20` | Must be numeric and > 0. |
| `CORS_ORIGINS` | Yes | `https://<app>.vercel.app` | Production UI origin. |
| `CORS_ORIGIN_REGEX` | For previews | `https://<project>.*\.vercel\.app` | Lets Vercel preview URLs call the API. |
| `PORT` | Injected | — | Railway sets this. The start command must use it. |

Missing or invalid `GROQ_API_KEY` does not crash the API. Recommendations still return, with `engine: "fallback"`.

### Vercel (frontend)

| Variable | Required | Example | Notes |
| --- | --- | --- | --- |
| `VITE_API_BASE` | Yes | `https://<service>.up.railway.app` | No trailing slash. Changing it requires a **new Vercel build**. |

Do not put `GROQ_API_KEY` in the frontend project. Vite exposes every `VITE_` variable in the browser bundle.

---

## 6. Deploy sequence

### 6.1 Railway first

1. Push the branch that contains the Dockerfile, `requirements-api.txt`, CORS env support, and `/health`.
2. Create a Railway project from this GitHub repo. Leave the root as the repository root (not `frontend/`).
3. Confirm the builder is Dockerfile, not Nixpacks. Nixpacks would see `requirements.txt` and would not run ingest.
4. Set the Railway variables from §5. Add a placeholder CORS origin if the Vercel URL does not exist yet, then update it in step 6.3.
5. Deploy. Wait until `/health` is green.
6. Copy the public URL (`https://<service>.up.railway.app`).
7. Smoke-test from a machine, before involving the browser:

```bash
curl https://<service>.up.railway.app/health
curl https://<service>.up.railway.app/meta
curl -X POST https://<service>.up.railway.app/recommendations \
  -H "Content-Type: application/json" \
  -d '{"locality":"Indiranagar","budget":"medium","cuisines":["Italian"],"min_rating":4.0,"extra_preferences":"family-friendly","max_results":5}'
```

`/meta` must return non-empty `localities`, `city_zones`, `cuisines`, and `budget_bands`. `/recommendations` must return `engine` of `llm` when the Groq key is valid, or `fallback` when it is not.

### 6.2 Vercel second

1. Import the same GitHub repo. Set Root Directory to `frontend`.
2. Set `VITE_API_BASE` to the Railway URL from step 6.1. Apply it to Production (and Preview, if previews should call the shared API).
3. Deploy. Open the Vercel URL.

### 6.3 Close the CORS loop

1. Put the real Vercel production URL into Railway `CORS_ORIGINS`.
2. Redeploy the API, or restart the service so the process reads the new variable. CORS is read at app creation, so a running process will not pick it up until restart.
3. Reload the Vercel site. The preference form must fill locality, zone, and cuisine from `/meta` without a browser CORS error.

### 6.4 Custom domains (optional)

1. Attach the domain on Vercel. Vercel issues the certificate.
2. Add `https://<custom-domain>` to `CORS_ORIGINS` and restart Railway.
3. Rebuild is not required unless `VITE_API_BASE` changes. A custom UI domain does not change the API URL.

---

## 7. Verification

Run these on the deployed URLs, not only locally.

| Check | Pass |
| --- | --- |
| `GET /health` | `200` and `{"status":"ok"}` |
| `GET /meta` from curl | Facet lists are populated |
| `POST /recommendations` from curl | Cards returned; `engine` is `llm` or `fallback` |
| Vercel page load | Form controls show dataset localities and cuisines |
| Submit a search | Cards render with explanations; summary is visible |
| Groq key removed, then restart Railway | Search still returns cards and the UI shows the heuristic fallback |
| Browser devtools | No CORS error; request host is the Railway URL, not the Vercel host |
| View page source / bundle | `GROQ_API_KEY` does not appear |
| Railway logs | Preference hash and engine are fine to log. Full prompts and the API key are not. |

Also submit once with an empty result (a very high min rating plus a rare cuisine) and confirm the empty state renders.

---

## 8. Operations

| Topic | Practice |
| --- | --- |
| Secrets | Rotate `GROQ_API_KEY` in the Groq console, update Railway, restart. No frontend rebuild. |
| Model swap | Change `GROQ_MODEL` on Railway and restart. No frontend rebuild. |
| API URL change | Update `VITE_API_BASE` and redeploy Vercel. The old bundle keeps the old URL until then. |
| Dataset refresh | Rebuild the Railway image so ingest runs again. |
| Cold start | First request after boot loads parquet. `/health` stays cheap; `/meta` is the slow one. |
| Cache | In-memory, 60 seconds, per process. A restart clears it. Do not expect it to be shared across replicas. |
| Replicas | Stay at one replica unless the store is loaded read-only and the cache being split is acceptable. Two replicas ≈ 2× RAM. |
| Logs | Railway: request latency, candidate count, `engine`. Do not log `GROQ_API_KEY` or raw review text. |
| Cost | Groq is billed per recommendation when `engine` is `llm`. Railway bills for the always-on container. Vercel bills for static bandwidth; this UI is small. |

### Rollback

- **Frontend:** Vercel → previous production deployment → Promote.
- **API:** Railway → previous successful deployment → Redeploy. The previous image still contains its baked parquet.
- CORS and `VITE_API_BASE` are independent. Rolling back only one side can leave the UI calling an origin the API does not allow. After any rollback, repeat the §7 browser check.

---

## 9. Out of scope for this deploy

- Streamlit on Railway or Vercel
- Putting FastAPI on Vercel serverless
- A Railway volume plus ingest-on-boot (use only if image-build ingest cannot reach Hugging Face)
- Committing `restaurants.parquet` to git
- Accounts, rate limits beyond the existing 60-second cache, or a live Zomato API
- CI deploy workflows. `.github/workflows/tests.yml` stays test-only. Deploy from the Railway and Vercel Git integrations.

---

## 10. Checklist

- [ ] `CORS_ORIGINS` (and preview regex, if used) read in `src/api/app.py`
- [ ] `GET /health` added and excluded from store load
- [ ] `requirements-api.txt` added
- [ ] Dockerfile builds parquet via `python -m src.ingest.load_hf`
- [ ] `railway.toml` points at the Dockerfile and `/health`
- [ ] Railway service is 1 GB, one replica, public URL copied
- [ ] `GROQ_API_KEY` set on Railway only
- [ ] curl checks for `/health`, `/meta`, and `/recommendations` pass
- [ ] Vercel root is `frontend`, `VITE_API_BASE` has no trailing slash
- [ ] Production origin added to `CORS_ORIGINS`, API restarted
- [ ] Browser: form loads, search returns cards, fallback still works with a bad Groq key
