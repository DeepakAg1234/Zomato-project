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
