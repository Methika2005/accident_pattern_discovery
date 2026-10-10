"""
app.py  --  Member 3: Flask backend & integration
=================================================

Loads the dataset once at startup, then serves:

    GET  /api/health              process + dataset status
    GET  /api/dataset/stats       preprocessing stats (filters, frequencies)
    GET  /api/dataset/preview     first n raw CSV rows
    GET  /api/mine                mine with query params
    POST /api/mine                mine with JSON body

Thresholds come from React as fractions (0.05) or percents (5).
"""

from __future__ import annotations

import os
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from apriori import AprioriError, run_apriori
from preprocessing import PreprocessingError, get_dataset_preview, load_and_preprocess

DATASET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "indian_roads_dataset.csv")

SEVERITY_ATTRIBUTE = "accident_severity"


class ApiError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _error_payload(message: str, status_code: int):
    return jsonify({"error": message, "status": status_code}), status_code


def _parse_threshold(value: Any, name: str) -> float:
    """Accept 0.05 or '5' / '5%' and return a fraction in (0, 1]."""
    if value is None or value == "":
        raise ApiError(f"{name} is required.")
    if isinstance(value, bool):
        raise ApiError(f"{name} must be a number.")
    if isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ApiError(f"{name} must be a number.") from exc
    if not isinstance(value, (int, float)):
        raise ApiError(f"{name} must be a number.")
    value = float(value)
    if value > 1:
        if value > 100:
            raise ApiError(f"{name} must be between 0 and 1, or a percentage 0-100.")
        value = value / 100.0
    if value <= 0 or value > 1:
        raise ApiError(f"{name} must be > 0 and <= 1 (or 1-100 as a percent).")
    return value


def _parse_exclude(value: Any) -> list[str]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return parts
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ApiError("exclude must be a list of attribute names.")
            out.append(item.strip())
        return out
    raise ApiError("exclude must be a list of attribute names.")


def _parse_max_k(value: Any) -> int:
    if value is None or value == "":
        return 4
    try:
        max_k = int(value)
    except (TypeError, ValueError) as exc:
        raise ApiError("max_k must be a positive integer.") from exc
    if max_k < 1:
        raise ApiError("max_k must be a positive integer.")
    return max_k


def _filter_transactions(transactions: list[set], exclude: list[str]) -> list[set]:
    if not exclude:
        return transactions
    unknown = [name for name in exclude if "=" in name]
    if unknown:
        raise ApiError(
            "exclude expects attribute names (e.g. 'city'), not item strings."
        )
    if SEVERITY_ATTRIBUTE in exclude:
        raise ApiError(f"{SEVERITY_ATTRIBUTE} cannot be excluded.")
    prefixes = tuple(f"{name}=" for name in exclude)
    filtered = []
    for txn in transactions:
        kept = {item for item in txn if not item.startswith(prefixes)}
        if kept:
            filtered.append(kept)
    if not filtered:
        raise ApiError("No transactions remained after applying exclude.")
    return filtered


def _mining_args():
    if request.method == "GET":
        payload = request.args
        min_support = payload.get("min_support", payload.get("support"))
        min_confidence = payload.get("min_confidence", payload.get("confidence"))
        exclude = payload.get("exclude")
        max_k = payload.get("max_k")
    else:
        payload = request.get_json(silent=True)
        if payload is None:
            if request.data:
                raise ApiError("Request body must be valid JSON.")
            payload = {}
        if not isinstance(payload, dict):
            raise ApiError("Request body must be a JSON object.")
        min_support = payload.get("min_support", payload.get("support"))
        min_confidence = payload.get("min_confidence", payload.get("confidence"))
        exclude = payload.get("exclude")
        max_k = payload.get("max_k")

    return {
        "min_support": _parse_threshold(min_support, "min_support"),
        "min_confidence": _parse_threshold(min_confidence, "min_confidence"),
        "exclude": _parse_exclude(exclude),
        "max_k": _parse_max_k(max_k),
    }


def create_app(dataset_path: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app)

    path = dataset_path or DATASET_PATH
    state: dict[str, Any] = {
        "path": path,
        "transactions": None,
        "stats": None,
        "error": None,
    }

    try:
        state["transactions"], state["stats"] = load_and_preprocess(path)
    except PreprocessingError as exc:
        state["error"] = str(exc)

    def require_dataset():
        if state["transactions"] is None:
            raise ApiError(
                state["error"] or "Dataset is not loaded.",
                status_code=503,
            )
        return state["transactions"], state["stats"]

    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return _error_payload(exc.message, exc.status_code)

    @app.errorhandler(AprioriError)
    def handle_apriori_error(exc: AprioriError):
        return _error_payload(str(exc), 400)

    @app.errorhandler(PreprocessingError)
    def handle_preproc_error(exc: PreprocessingError):
        return _error_payload(str(exc), 400)

    @app.errorhandler(404)
    def handle_404(_exc):
        return _error_payload("Not found.", 404)

    @app.errorhandler(405)
    def handle_405(_exc):
        return _error_payload("Method not allowed.", 405)

    @app.errorhandler(500)
    def handle_500(_exc):
        return _error_payload("Internal server error.", 500)

    @app.get("/api/health")
    def health():
        loaded = state["transactions"] is not None
        body = {
            "status": "ok" if loaded else "error",
            "project": "accident_pattern_discovery",
            "dataset_loaded": loaded,
            "transaction_count": (
                state["stats"]["transaction_count"] if state["stats"] else 0
            ),
        }
        if state["error"]:
            body["error"] = state["error"]
        return jsonify(body), (200 if loaded else 503)

    @app.get("/api/dataset/stats")
    def dataset_stats():
        _tx, stats = require_dataset()
        return jsonify(stats)

    @app.get("/api/dataset/preview")
    def dataset_preview():
        n = request.args.get("n", 10)
        try:
            n = int(n)
        except (TypeError, ValueError):
            raise ApiError("n must be an integer.")
        try:
            preview = get_dataset_preview(state["path"], n=n)
        except PreprocessingError as exc:
            raise ApiError(str(exc), status_code=503)
        return jsonify(preview)

    @app.route("/api/mine", methods=["GET", "POST"])
    def mine():
        transactions, stats = require_dataset()
        args = _mining_args()
        working = _filter_transactions(transactions, args["exclude"])
        result = run_apriori(
            working,
            min_support=args["min_support"],
            min_confidence=args["min_confidence"],
            max_k=args["max_k"],
        )
        result["dataset"] = {
            "source_file": stats.get("source_file"),
            "transaction_count": stats.get("transaction_count"),
            "distinct_item_count": stats.get("distinct_item_count"),
            "attributes_used": stats.get("attributes_used"),
            "attribute_values": stats.get("attribute_values"),
            "excluded_for_this_run": args["exclude"],
        }
        result["disclaimer"] = (
            "These are patterns in this dataset, not real-world findings "
            "or causal claims."
        )
        return jsonify(result)

    return app


# Flask CLI (`flask --app app run`) resolves `app` lazily so unit tests can
# import create_app() without loading the 20k-row CSV.
_cached_app = None


def __getattr__(name: str):
    global _cached_app
    if name == "app":
        if _cached_app is None:
            _cached_app = create_app()
        return _cached_app
    raise AttributeError(name)


if __name__ == "__main__":
    create_app().run(debug=True, port=5000)
