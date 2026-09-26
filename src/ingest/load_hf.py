"""One-time ingest: Hugging Face → clean → `data/processed/restaurants.parquet`.

Run with `python -m src.ingest.load_hf`. Never call this from a request path.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

from src.ingest.clean import build_facets, clean_dataframe

DATASET_NAME = "ManikaSaini/zomato-restaurant-recommendation"
DATASET_SPLIT = "train"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PARQUET_PATH = PROCESSED_DIR / "restaurants.parquet"
FACETS_PATH = PROCESSED_DIR / "facets.json"

DROPPED_RAW_COLUMNS = ("menu_item", "phone")


def load_raw(cache_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Download (or reuse the cached copy of) the dataset as a DataFrame."""
    from datasets import load_dataset

    cache_dir.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset(DATASET_NAME, split=DATASET_SPLIT, cache_dir=str(cache_dir))
    dropped = [col for col in DROPPED_RAW_COLUMNS if col in dataset.column_names]
    if dropped:
        dataset = dataset.remove_columns(dropped)
    return dataset.to_pandas()


def _atomic_write(path: Path, write) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        write(tmp_path)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def write_outputs(
    df: pd.DataFrame,
    parquet_path: Path = PARQUET_PATH,
    facets_path: Path = FACETS_PATH,
) -> dict[str, list[str]]:
    facets = build_facets(df)
    _atomic_write(parquet_path, lambda p: df.to_parquet(p, index=False))
    _atomic_write(
        facets_path,
        lambda p: p.write_text(json.dumps(facets, ensure_ascii=False, indent=2), encoding="utf-8"),
    )
    return facets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output", type=Path, default=PARQUET_PATH)
    parser.add_argument("--facets", type=Path, default=FACETS_PATH)
    args = parser.parse_args(argv)

    print(f"Loading {DATASET_NAME} [{DATASET_SPLIT}] ...")
    try:
        raw = load_raw(args.cache_dir)
    except Exception as exc:
        print(
            f"ERROR: could not load the dataset from Hugging Face ({type(exc).__name__}: {exc}).\n"
            "Check your network connection and re-run; no processed files were written.",
            file=sys.stderr,
        )
        return 1

    df, stats = clean_dataframe(raw)
    facets = write_outputs(df, args.output, args.facets)

    print(f"Raw rows:            {stats.raw_rows:>7,}")
    print(f"After clean:         {stats.cleaned_rows:>7,}")
    print(f"After dedupe:        {stats.deduped_rows:>7,}")
    print(
        f"Facets:              {len(facets['localities'])} localities, "
        f"{len(facets['city_zones'])} city zones, {len(facets['cuisines'])} cuisines"
    )
    print(f"Wrote {args.output}")
    print(f"Wrote {args.facets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
