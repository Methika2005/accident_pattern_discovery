# API Contract Documentation

## Overview
The backend Flask API serves endpoints for preprocessing data inspection and Apriori association rule mining.

Base URL: `http://localhost:5000`

---

## Endpoints

### 1. Health Check
- **Endpoint**: `GET /api/health`
- **Description**: Returns process and dataset load status.
- **Response** (`200 OK` or `503 Service Unavailable`):
  ```json
  {
    "status": "ok",
    "project": "accident_pattern_discovery",
    "dataset_loaded": true,
    "transaction_count": 20000
  }
  ```

---

### 2. Dataset Stats
- **Endpoint**: `GET /api/dataset/stats`
- **Description**: Returns preprocessing metadata, transaction counts, attribute value lists (for dropdown filters), and item frequencies.
- **Response** (`200 OK`):
  ```json
  {
    "transaction_count": 20000,
    "distinct_item_count": 62,
    "attributes_used": ["city", "road_type", "weather", ...],
    "attributes_excluded": ["casualties", "risk_score", "state", "visibility", "is_weekend"],
    "attribute_values": {
      "weather": ["rain", "fog", "clear"],
      "accident_severity": ["fatal", "major", "minor"]
    },
    "item_frequencies": { ... }
  }
  ```

---

### 3. Dataset Preview
- **Endpoint**: `GET /api/dataset/preview?n=10`
- **Parameters**: `n` (optional integer, defaults to 10).
- **Description**: Returns raw CSV column headers and the first `n` rows.
- **Response** (`200 OK`):
  ```json
  {
    "row_count": 20000,
    "columns": ["accident_id", "city", ...],
    "rows": [ ... ]
  }
  ```

---

### 4. Apriori Rule Mining
- **Endpoint**: `POST /api/mine` or `GET /api/mine`
- **Parameters / JSON Body**:
  - `min_support` (or `support`): Minimum support threshold as a fraction `(0.01 to 1.0]` or percentage `(1% to 100%)`. **Floor is strictly 1% (0.01)**.
  - `min_confidence` (or `confidence`): Minimum confidence threshold as a fraction `(0.0 to 1.0]` or percentage `(0% to 100%)`.
  - `max_k`: Maximum size of frequent itemsets. Defaults to `4`. Pass `null`, `"none"`, `"unlimited"` for no size limit.
  - `exclude`: Optional list of column attribute names to exclude from transactions (e.g. `["city"]`).
- **Response** (`200 OK`):
  - `association_rules`: List of rules sorted by lift (descending), **capped at the top 500 rules**.
  - `frequent_itemsets`: List of discovered frequent itemsets with size, count, and support.
  - `metrics`:
    - `min_support`: float
    - `min_confidence`: float
    - `transaction_count`: int
    - `distinct_item_count`: int
    - `frequent_itemset_count`: int
    - `rule_count`: int (true total number of rules discovered)
    - `rules_returned`: int (number of rules returned in response, capped at 500)
    - `rules_capped`: bool (`true` if total rules exceeded 500)
    - `max_rules_returned`: int (`500`)
    - `max_k`: int or null
    - `elapsed_seconds`: float
  - `dataset`: Metadata on current run transactions.
  - `disclaimer`: Contextual guidance warning on synthetic data.

---

## Error Handling
Errors return standard JSON structure with HTTP status code `400` or `500`/`503`:
```json
{
  "error": "min_support cannot be lower than 0.01 (1%).",
  "status": 400
}
```
