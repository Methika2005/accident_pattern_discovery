# Dataset source and preprocessing notes (Member 2)

## Source
- **Name:** Indian Road Accident Dataset 2022-2025
- **Kaggle:** https://www.kaggle.com/datasets/sehaj1104/indian-road-accident-dataset-20222025
- **File used:** `backend/data/indian_roads_dataset.csv`
- **Size:** 20,000 rows x 24 columns, dates 2022-01-01 to 2025-04-15, 8 cities in 7 states.

## Provenance and limitations (must appear in the report)
The Kaggle page does not state how the records were collected, and the data
itself looks **synthetic or simulated**, not official police records:
- Categories are almost perfectly evenly distributed (e.g. each of the 3 road
  types is about 33%, each of the 5 causes about 20%, each of the 6 lane counts about 17%).
- `weather` fully determines `visibility`, and `city` fully determines `state`.
- `cause = weather` occurs equally often in clear, fog and rain.

So any rule found should be described as **a pattern in this dataset**, not as
a real-world finding about Indian roads. Apriori finds associations, not causes.
Expect many rules with lift close to 1.0 - that is a property of the data, and
reporting it honestly is a valid result.

## Columns

| Column | Used? | Treatment |
|---|---|---|
| accident_id | No | Identifier, unique per row |
| city | Yes | `city=pune` |
| state | No | Duplicate of `city` |
| latitude, longitude | No | Raw coordinates, not categories |
| date | Derived | Month -> `season` (winter / summer / monsoon / post_monsoon) |
| time, hour | Derived | Hour -> `time_of_day` (night 0-5, morning 6-11, afternoon 12-17, evening 18-23) |
| day_of_week | Yes | `day_of_week=sunday` |
| is_weekend | No | Duplicate of `day_of_week` |
| road_type | Yes | highway / rural / urban |
| lanes | Yes | `lanes=1` ... `lanes=6` |
| traffic_signal | Yes | yes / no |
| weather | Yes | clear / fog / rain |
| visibility | No | Fully determined by `weather` (would give trivial rules) |
| temperature | Derived | cool (<=22), warm (23-31), hot (>=32) |
| traffic_density | Yes | low / medium / high |
| cause | Yes | distraction / drunk_driving / overspeeding / poor_road / weather |
| accident_severity | Yes | minor / major / fatal |
| vehicles_involved | Yes | `vehicles_involved=1` ... `5` |
| casualties | No | Outcome of the accident (leakage) |
| is_peak_hour | Yes | yes / no |
| festival | Yes | holi / eid / diwali / new_year; **"None" (99.4% of rows) produces no item** |
| risk_score | No | Derived score that already encodes severity (leakage) |

15 attributes are mined, giving 62 distinct items and about 14 items per transaction.

## Cleaning rules
- Everything is read as text, so the literal string `None` in `festival` is not turned into NaN.
- Values are trimmed, lower-cased, and inner spaces become `_` (`drunk driving` -> `drunk_driving`).
- `""`, `nan`, `null`, `n/a`, `unknown`, `?`, `-` count as missing: that cell gives no item, but the record is kept.
- Records with no usable `accident_severity` are dropped, since every rule is about severity.
- Exact duplicates (ignoring `accident_id`) are dropped. Empty transactions are never emitted.
- Result on this file: 0 rows dropped, 20,000 transactions.

## Interface
```python
from preprocessing import load_and_preprocess, get_dataset_preview, PreprocessingError

transactions, stats = load_and_preprocess("data/indian_roads_dataset.csv")
# transactions: list[set[str]]  e.g. {"weather=fog", "road_type=highway", "accident_severity=fatal"}
# optional: load_and_preprocess(path, exclude=["city", "day_of_week"])
```
`stats` is JSON-serialisable and contains: `source_file`, `raw_row_count`, `transaction_count`,
`dropped_rows`, `attributes_used`, `attributes_excluded` (with reasons), `missing_values_per_attribute`,
`distinct_item_count`, `avg_items_per_transaction`, `attribute_values` (for the UI filters) and
`item_frequencies` (item, count, support).
`PreprocessingError` (a `ValueError`) is raised for a missing, empty or malformed file or missing
required columns; the API should catch it and return HTTP 400/500 with its message.