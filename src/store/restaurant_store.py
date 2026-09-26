"""In-memory restaurant store backed by the processed parquet file.

Load once per process (e.g. `st.cache_resource`); never re-ingest from here.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ingest.clean import build_facets
from src.ingest.load_hf import FACETS_PATH, PARQUET_PATH
from src.models import Restaurant

LIST_COLUMNS = ("cuisines", "rest_types", "dishes_liked")


class StoreNotReadyError(RuntimeError):
    """Processed data is missing or unreadable; ingest must be run first."""


class RestaurantStore:
    def __init__(self, df: pd.DataFrame, facets: dict[str, list[str]] | None = None):
        df = df.copy()
        for col in LIST_COLUMNS:
            df[col] = df[col].map(lambda v: [] if v is None else [str(x) for x in v])
        self.df = df.reset_index(drop=True)
        self.facets = facets if facets is not None else build_facets(self.df)

        self._row_by_id = {rid: i for i, rid in enumerate(self.df["id"])}
        self.by_locality = self._index(self.df["locality"])
        self.by_city_zone = self._index(self.df["city_zone"])
        self.by_cuisine: dict[str, list[int]] = {}
        for i, items in enumerate(self.df["cuisines"]):
            for cuisine in {c.lower() for c in items}:
                self.by_cuisine.setdefault(cuisine, []).append(i)

        self.zones_by_locality: dict[str, list[str]] = {}
        for locality, zone in zip(self.df["locality"], self.df["city_zone"]):
            if locality and zone:
                zones = self.zones_by_locality.setdefault(locality.lower(), [])
                if zone.lower() not in zones:
                    zones.append(zone.lower())

    @staticmethod
    def _index(values: pd.Series) -> dict[str, list[int]]:
        index: dict[str, list[int]] = {}
        for i, value in enumerate(values):
            if value:
                index.setdefault(value.lower(), []).append(i)
        return index

    @classmethod
    def load(
        cls,
        parquet_path: Path = PARQUET_PATH,
        facets_path: Path = FACETS_PATH,
    ) -> RestaurantStore:
        if not parquet_path.exists():
            raise StoreNotReadyError(
                f"{parquet_path} not found. Run `python -m src.ingest.load_hf` first."
            )
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:
            raise StoreNotReadyError(
                f"Could not read {parquet_path} ({exc}). Re-run `python -m src.ingest.load_hf`."
            ) from exc

        facets = None
        if facets_path.exists():
            facets = json.loads(facets_path.read_text(encoding="utf-8"))
        return cls(df, facets)

    def __len__(self) -> int:
        return len(self.df)

    def get(self, restaurant_id: str) -> Restaurant | None:
        row = self._row_by_id.get(restaurant_id)
        return None if row is None else self.to_restaurant(row)

    def to_restaurant(self, row: int) -> Restaurant:
        record = self.df.iloc[row].to_dict()
        return Restaurant(**{k: _to_python(v) for k, v in record.items()})


def _to_python(value):
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value
