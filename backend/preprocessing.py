"""
preprocessing.py  --  Member 2: Dataset & Preprocessing
=======================================================

Turns the Indian road accident CSV into *transactions* for the Apriori engine.

Public interface (agreed with Members 1 and 3)
----------------------------------------------
    load_and_preprocess(csv_path) -> (transactions, stats)

        transactions : list[set[str]]   one set of "column=value" items per
                                        retained accident record
        stats        : dict (JSON-serialisable, safe to pass to jsonify)

Extra helpers for the API / UI
------------------------------
    get_dataset_preview(csv_path, n=10) -> dict   first n raw rows for the UI
    PreprocessingError                            raised on bad input

What the pipeline does
----------------------
1. Reads every column as text (so "None" in `festival` is not silently turned
   into NaN by pandas) and validates that the required columns exist.
2. Cleans values: trims whitespace, lower-cases, collapses inner spaces and
   maps junk tokens ("", "nan", "null", "n/a", "unknown", "?") to *missing*.
3. Derives a few mining-friendly attributes from raw ones:
       hour        -> time_of_day   (night / morning / afternoon / evening)
       date        -> season        (winter / summer / monsoon / post_monsoon)
       temperature -> temperature   (cool / warm / hot)
4. Builds one transaction per record from the selected categorical columns.
   Missing cells simply produce no item (the record is kept).  Records without
   a usable severity are dropped, because every rule is about severity.
5. Never mines identifiers, coordinates, raw dates/times, or fields that leak
   the outcome (see EXCLUDED_COLUMNS for the reason for each one).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from typing import Iterable

import pandas as pd


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

#: Columns that must exist in the CSV, otherwise we refuse to run.
REQUIRED_COLUMNS = [
    "road_type", "weather", "traffic_density", "cause", "accident_severity",
    "is_peak_hour",
]

#: Column that every retained record must have (rules are about severity).
SEVERITY_COLUMN = "accident_severity"

#: Columns used as items, in the order they appear in a transaction.
#: Value = how the column is turned into an item (see _build_item_frame).
ITEM_COLUMNS = [
    "city",
    "road_type",
    "lanes",
    "traffic_signal",
    "weather",
    "temperature",
    "traffic_density",
    "time_of_day",
    "is_peak_hour",
    "day_of_week",
    "season",
    "festival",
    "vehicles_involved",
    "cause",
    "accident_severity",
]

#: Columns deliberately NOT mined, with the reason (also returned in stats).
EXCLUDED_COLUMNS = {
    "accident_id": "identifier - unique per row, can never form a frequent itemset",
    "latitude": "raw coordinate - numeric and unique-ish, not a category",
    "longitude": "raw coordinate - numeric and unique-ish, not a category",
    "date": "raw date - replaced by the derived 'season' attribute",
    "time": "raw time - replaced by the derived 'time_of_day' attribute",
    "hour": "raw hour - replaced by the derived 'time_of_day' attribute",
    "state": "fully determined by 'city' in this dataset - duplicates information",
    "is_weekend": "fully determined by 'day_of_week' - duplicates information",
    "visibility": "fully determined by 'weather' in this dataset - gives trivial rules",
    "casualties": "outcome of the accident (leakage) - correlates with severity",
    "risk_score": "derived score that already encodes severity (leakage)",
}

#: Values (after lower-casing) that mean "no information".
MISSING_TOKENS = {"", "nan", "null", "n/a", "na", "unknown", "?", "-", "--"}

#: In `festival`, "none" means "no festival", which is *not* worth an item
#: (99%+ of rows would carry it and it would swamp every real pattern).
NO_FESTIVAL_TOKENS = {"none", "no", "no festival"}

SEASONS = {  # month -> season (Indian climate calendar)
    12: "winter", 1: "winter", 2: "winter",
    3: "summer", 4: "summer", 5: "summer",
    6: "monsoon", 7: "monsoon", 8: "monsoon", 9: "monsoon",
    10: "post_monsoon", 11: "post_monsoon",
}


class PreprocessingError(ValueError):
    """Raised when the CSV is missing, empty, or lacks required columns."""


# --------------------------------------------------------------------------
# Cleaning helpers
# --------------------------------------------------------------------------

def _clean_text(series: pd.Series) -> pd.Series:
    """Trim, lower-case, collapse spaces; junk tokens become <NA>."""
    s = series.astype("string").str.strip().str.lower()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.mask(s.isin(MISSING_TOKENS))


def _to_number(series: pd.Series) -> pd.Series:
    """Parse numbers; anything unparsable becomes NaN."""
    return pd.to_numeric(_clean_text(series), errors="coerce")


def _bin_time_of_day(hour: pd.Series) -> pd.Series:
    h = hour.where((hour >= 0) & (hour <= 23))
    out = pd.Series(pd.NA, index=h.index, dtype="string")
    out[h.between(0, 5)] = "night"
    out[h.between(6, 11)] = "morning"
    out[h.between(12, 17)] = "afternoon"
    out[h.between(18, 23)] = "evening"
    return out


def _bin_temperature(temp: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=temp.index, dtype="string")
    out[temp <= 22] = "cool"
    out[(temp > 22) & (temp < 32)] = "warm"
    out[temp >= 32] = "hot"
    return out


def _season_from_date(date: pd.Series) -> pd.Series:
    month = pd.to_datetime(_clean_text(date), format="ISO8601", errors="coerce").dt.month
    return month.map(SEASONS).astype("string")


def _yes_no(series: pd.Series) -> pd.Series:
    """0/1 flags (also accepts yes/no/true/false) -> 'no' / 'yes'."""
    s = _clean_text(series)
    mapping = {"1": "yes", "1.0": "yes", "yes": "yes", "true": "yes", "y": "yes",
               "0": "no", "0.0": "no", "no": "no", "false": "no", "n": "no"}
    return s.map(mapping).astype("string")


def _whole_number_text(series: pd.Series) -> pd.Series:
    """'4', '4.0' -> '4'; unparsable -> <NA>."""
    num = _to_number(series)
    num = num.where(num >= 0)
    return num.round().astype("Int64").astype("string")


# --------------------------------------------------------------------------
# Item frame: one cleaned categorical column per mined attribute
# --------------------------------------------------------------------------

def _build_item_frame(raw: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Return a frame with one cleaned categorical column per attribute."""
    cols = {}
    for name in columns:
        if name == "time_of_day":
            if "hour" in raw:
                hour = _to_number(raw["hour"])
            elif "time" in raw:  # fall back to "13:00" style strings
                hour = pd.to_numeric(
                    _clean_text(raw["time"]).str.split(":").str[0], errors="coerce")
            else:
                continue
            cols[name] = _bin_time_of_day(hour)
        elif name == "season":
            if "date" in raw:
                cols[name] = _season_from_date(raw["date"])
        elif name == "temperature":
            if "temperature" in raw:
                cols[name] = _bin_temperature(_to_number(raw["temperature"]))
        elif name in ("traffic_signal", "is_peak_hour"):
            if name in raw:
                cols[name] = _yes_no(raw[name])
        elif name in ("lanes", "vehicles_involved"):
            if name in raw:
                cols[name] = _whole_number_text(raw[name])
        elif name == "festival":
            if name in raw:
                s = _clean_text(raw[name])
                cols[name] = s.mask(s.isin(NO_FESTIVAL_TOKENS)).str.replace(" ", "_", regex=False)
        elif name in raw:
            cols[name] = _clean_text(raw[name]).str.replace(" ", "_", regex=False)
    return pd.DataFrame(cols, index=raw.index)


def _row_to_items(row: pd.Series) -> set:
    return {f"{col}={val}" for col, val in row.items() if pd.notna(val)}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _read_csv(csv_path: str) -> pd.DataFrame:
    if not csv_path or not os.path.isfile(csv_path):
        raise PreprocessingError(f"Dataset file not found: {csv_path!r}")
    try:
        # dtype=str + keep_default_na=False: "None" in `festival` stays text.
        raw = pd.read_csv(csv_path, dtype=str, keep_default_na=False,
                          skipinitialspace=True)
    except pd.errors.EmptyDataError as exc:
        raise PreprocessingError("Dataset file is empty.") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise PreprocessingError(f"Could not parse CSV: {exc}") from exc
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    if raw.empty:
        raise PreprocessingError("Dataset has a header but no rows.")
    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise PreprocessingError(
            "Dataset is missing required column(s): " + ", ".join(missing))
    return raw


def load_and_preprocess(csv_path: str, exclude: Iterable[str] | None = None):
    """
    Read the accident CSV and convert every retained record to a transaction.

    Parameters
    ----------
    csv_path : path to the CSV file.
    exclude  : optional attribute names to leave out of the transactions
               (e.g. ["city", "day_of_week"]); 'accident_severity' cannot
               be excluded.

    Returns
    -------
    transactions : list[set[str]]  e.g. {"weather=rain", "road_type=highway"}
    stats        : dict            JSON-serialisable summary (see below)

    Raises
    ------
    PreprocessingError  if the file is missing/empty/unparsable or required
                        columns are absent.
    """
    raw = _read_csv(csv_path)
    total_rows = len(raw)

    excluded_by_user = set(exclude or []) - {SEVERITY_COLUMN}
    unknown = excluded_by_user - set(ITEM_COLUMNS)
    if unknown:
        raise PreprocessingError(
            "Unknown attribute(s) in exclude: " + ", ".join(sorted(unknown)))
    columns = [c for c in ITEM_COLUMNS if c not in excluded_by_user]

    items = _build_item_frame(raw, columns)

    # Records must carry a usable severity; everything else may be missing.
    no_severity = items[SEVERITY_COLUMN].isna()
    dropped_no_severity = int(no_severity.sum())
    items = items[~no_severity]

    # Exact duplicates of everything except the id add nothing but weight.
    content_cols = [c for c in raw.columns if c != "accident_id"]
    dup_mask = raw.loc[items.index, content_cols].duplicated(keep="first")
    dropped_duplicates = int(dup_mask.sum())
    items = items[~dup_mask]

    # Transactions
    transactions = [_row_to_items(row) for _, row in items.iterrows()]
    transactions = [t for t in transactions if t]  # never emit an empty basket
    dropped_empty = len(items) - len(transactions)

    # ---- statistics ------------------------------------------------------
    item_counts = Counter(i for t in transactions for i in t)
    n = len(transactions)
    attribute_values = {
        col: sorted(items[col].dropna().unique().tolist())
        for col in items.columns
    }
    stats = {
        "source_file": os.path.basename(csv_path),
        "raw_row_count": int(total_rows),
        "transaction_count": int(n),
        "dropped_rows": {
            "missing_severity": dropped_no_severity,
            "duplicates": dropped_duplicates,
            "empty_transaction": int(dropped_empty),
        },
        "attributes_used": list(items.columns),
        "attributes_excluded": {
            **EXCLUDED_COLUMNS,
            **{c: "excluded by user request" for c in sorted(excluded_by_user)},
        },
        "missing_values_per_attribute": {
            col: int(items[col].isna().sum()) for col in items.columns
        },
        "distinct_item_count": len(item_counts),
        "avg_items_per_transaction": round(
            sum(len(t) for t in transactions) / n, 3) if n else 0.0,
        "attribute_values": attribute_values,
        "item_frequencies": [
            {"item": item, "count": int(c), "support": round(c / n, 4)}
            for item, c in sorted(item_counts.items(),
                                  key=lambda kv: (-kv[1], kv[0]))
        ] if n else [],
    }
    if n == 0:
        raise PreprocessingError("No usable records remained after cleaning.")
    return transactions, stats


def get_dataset_preview(csv_path: str, n: int = 10) -> dict:
    """First `n` raw rows, for the UI's dataset preview table."""
    raw = _read_csv(csv_path)
    n = max(1, min(int(n), 100))
    head = raw.head(n)
    return {
        "columns": list(raw.columns),
        "row_count": int(len(raw)),
        "rows": head.to_dict(orient="records"),
    }


if __name__ == "__main__":  # quick manual check:  python preprocessing.py data/indian_roads_dataset.csv
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "data", "indian_roads_dataset.csv")
    tx, st = load_and_preprocess(path)
    st.pop("item_frequencies")
    print(json.dumps(st, indent=2))
    print("First transaction:", sorted(tx[0]))