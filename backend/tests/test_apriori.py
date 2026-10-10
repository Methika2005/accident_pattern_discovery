"""Tests for backend/apriori.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apriori import AprioriError, run_apriori  # noqa: E402
from preprocessing import load_and_preprocess  # noqa: E402

REAL_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "indian_roads_dataset.csv",
)


class TestAprioriToy(unittest.TestCase):
    def setUp(self):
        # 4 transactions. a: 100%, b: 75%, c: 50%, {a,b}: 75%, {a,c}: 50%, {b,c}: 25%
        self.tx = [
            {"a", "b", "c"},
            {"a", "b"},
            {"a", "b"},
            {"a", "c"},
        ]

    def test_rejects_bad_thresholds(self):
        with self.assertRaises(AprioriError):
            run_apriori(self.tx, min_support=0, min_confidence=0.5)
        with self.assertRaises(AprioriError):
            run_apriori(self.tx, min_support=1.5, min_confidence=0.5)
        with self.assertRaises(AprioriError):
            run_apriori(self.tx, min_support=0.5, min_confidence=0)

    def test_empty_transactions(self):
        with self.assertRaises(AprioriError):
            run_apriori([], min_support=0.5, min_confidence=0.5)

    def test_frequent_itemsets_and_json_shape(self):
        result = run_apriori(self.tx, min_support=0.5, min_confidence=0.5)
        itemsets = {tuple(row["items"]): row for row in result["frequent_itemsets"]}
        self.assertIn(("a",), itemsets)
        self.assertIn(("b",), itemsets)
        self.assertIn(("c",), itemsets)
        self.assertIn(("a", "b"), itemsets)
        self.assertIn(("a", "c"), itemsets)
        self.assertNotIn(("b", "c"), itemsets)
        self.assertEqual(itemsets[("a",)]["support"], 1.0)
        self.assertEqual(itemsets[("a", "b")]["count"], 3)
        self.assertEqual(result["metrics"]["transaction_count"], 4)
        self.assertTrue(result["association_rules"])
        rule = result["association_rules"][0]
        for key in ("antecedent", "consequent", "support", "confidence", "lift"):
            self.assertIn(key, rule)

    def test_confidence_and_lift(self):
        result = run_apriori(self.tx, min_support=0.5, min_confidence=0.6)
        # b => a : support 0.75, confidence 1.0, lift 1.0
        match = [
            r for r in result["association_rules"]
            if r["antecedent"] == ["b"] and r["consequent"] == ["a"]
        ]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0]["confidence"], 1.0)
        self.assertEqual(match[0]["lift"], 1.0)
        # c => a is confidence 1.0 as well; a => c is 0.5 and should be dropped
        a_to_c = [
            r for r in result["association_rules"]
            if r["antecedent"] == ["a"] and r["consequent"] == ["c"]
        ]
        self.assertEqual(a_to_c, [])


@unittest.skipUnless(os.path.isfile(REAL_CSV), "dataset missing")
class TestAprioriOnRealData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tx, cls.stats = load_and_preprocess(REAL_CSV)

    def test_reference_supports(self):
        result = run_apriori(self.tx, min_support=0.10, min_confidence=0.50)
        by_item = {
            row["items"][0]: row["support"]
            for row in result["frequent_itemsets"] if row["size"] == 1
        }
        self.assertAlmostEqual(by_item["accident_severity=fatal"], 0.1494, places=3)
        self.assertAlmostEqual(by_item["accident_severity=major"], 0.2994, places=3)
        self.assertAlmostEqual(by_item["accident_severity=minor"], 0.5513, places=3)
        self.assertAlmostEqual(by_item["weather=rain"], 0.3338, places=3)
        self.assertGreaterEqual(result["metrics"]["max_itemset_size"], 1)
        self.assertEqual(result["metrics"]["transaction_count"], 20000)


if __name__ == "__main__":
    unittest.main()
