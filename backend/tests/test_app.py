"""Tests for backend/app.py (Flask API)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

HEADER = (
    "accident_id,city,state,latitude,longitude,date,time,hour,day_of_week,"
    "is_weekend,road_type,lanes,traffic_signal,weather,visibility,temperature,"
    "traffic_density,cause,accident_severity,vehicles_involved,casualties,"
    "is_peak_hour,festival,risk_score"
)
ROW_A = (
    "0,Pune,Maharashtra,18.68,73.93,2023-10-22,5:00,5,Sunday,1,highway,3,1,"
    "fog,low,32,high,weather,fatal,2,2,0,None,0.85"
)
ROW_B = (
    "1,Mumbai,Maharashtra,18.81,72.79,2023-05-21,18:00,18,Monday,0,urban,4,0,"
    "clear,high,20,low,drunk driving,minor,4,3,1,Holi,0.1"
)
ROW_C = (
    "2,Pune,Maharashtra,18.70,73.90,2023-10-23,5:00,5,Sunday,1,highway,3,1,"
    "fog,low,32,high,weather,fatal,2,2,0,None,0.80"
)


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join([HEADER, ROW_A, ROW_B, ROW_C]) + "\n")
        self.addCleanup(os.remove, path)
        self.app = create_app(dataset_path=path)
        self.client = self.app.test_client()

    def test_health_ok(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["dataset_loaded"])
        self.assertEqual(body["transaction_count"], 3)

    def test_stats_has_filter_values(self):
        res = self.client.get("/api/dataset/stats")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("attribute_values", body)
        self.assertIn("weather", body["attribute_values"])
        self.assertIn("item_frequencies", body)

    def test_preview(self):
        res = self.client.get("/api/dataset/preview?n=2")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertEqual(body["row_count"], 3)
        self.assertEqual(len(body["rows"]), 2)
        self.assertIn("columns", body)

    def test_mine_post_returns_rules(self):
        res = self.client.post(
            "/api/mine",
            data=json.dumps({"min_support": 0.5, "min_confidence": 0.5}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertIn("frequent_itemsets", body)
        self.assertIn("association_rules", body)
        self.assertIn("metrics", body)
        self.assertGreater(body["metrics"]["frequent_itemset_count"], 0)
        self.assertIn("disclaimer", body)

    def test_mine_get_accepts_percent(self):
        res = self.client.get("/api/mine?min_support=50&min_confidence=50")
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        self.assertEqual(res.get_json()["metrics"]["min_support"], 0.5)

    def test_missing_thresholds_are_400(self):
        res = self.client.post(
            "/api/mine",
            data=json.dumps({"min_support": 0.2}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("min_confidence", res.get_json()["error"])

    def test_invalid_support_is_400(self):
        res = self.client.post(
            "/api/mine",
            data=json.dumps({"min_support": 0, "min_confidence": 0.5}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_invalid_json_is_400(self):
        res = self.client.post(
            "/api/mine",
            data="{not-json",
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_cannot_exclude_severity(self):
        res = self.client.post(
            "/api/mine",
            data=json.dumps({
                "min_support": 0.5,
                "min_confidence": 0.5,
                "exclude": ["accident_severity"],
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_unknown_route(self):
        res = self.client.get("/api/nope")
        self.assertEqual(res.status_code, 404)


class MissingDatasetApiTest(unittest.TestCase):
    def test_health_503_when_csv_missing(self):
        app = create_app(dataset_path="data/does_not_exist.csv")
        res = app.test_client().get("/api/health")
        self.assertEqual(res.status_code, 503)
        self.assertFalse(res.get_json()["dataset_loaded"])


if __name__ == "__main__":
    unittest.main()
