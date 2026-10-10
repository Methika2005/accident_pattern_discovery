"""Tests for backend/apriori.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random  # noqa: E402
from itertools import combinations  # noqa: E402

from apriori import (  # noqa: E402
    AprioriError,
    _generate_candidates,
    apriori,
    generate_rules,
    run_apriori,
)
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


class TestPruning(unittest.TestCase):
    def test_candidate_with_infrequent_subset_is_pruned(self):
        # Items 0,1,2.  L2 = {(0,1), (0,2)}; (1,2) is NOT frequent.
        # Joining gives (0,1,2) but its subset (1,2) is missing -> pruned.
        self.assertEqual(_generate_candidates([(0, 1), (0, 2)], 3), [])

    def test_candidate_kept_when_all_subsets_frequent(self):
        self.assertEqual(
            _generate_candidates([(0, 1), (0, 2), (1, 2)], 3), [(0, 1, 2)]
        )

    def test_infrequent_item_never_appears_in_any_itemset(self):
        tx = [{"a", "b"}, {"a", "b"}, {"a", "b"}, {"a", "z"}]  # z: 25%
        result = run_apriori(tx, min_support=0.5, min_confidence=0.1)
        for row in result["frequent_itemsets"]:
            self.assertNotIn("z", row["items"])


class TestHandCalculatedMetrics(unittest.TestCase):
    def setUp(self):
        # N=10. rain=5, fatal=4, {rain,fatal}=3
        self.tx = (
            [{"rain", "fatal"}] * 3
            + [{"rain", "minor"}] * 2
            + [{"clear", "fatal"}] * 1
            + [{"clear", "minor"}] * 4
        )

    def test_rain_implies_fatal(self):
        result = run_apriori(self.tx, min_support=0.3, min_confidence=0.5)
        rule = next(
            r for r in result["association_rules"]
            if r["antecedent"] == ["rain"] and r["consequent"] == ["fatal"]
        )
        self.assertAlmostEqual(rule["support"], 0.3)        # 3/10
        self.assertAlmostEqual(rule["confidence"], 0.6)     # 3/5
        self.assertAlmostEqual(rule["lift"], 1.5)           # 0.6 / 0.4
        self.assertEqual(rule["count"], 3)

    def test_threshold_exactly_equal_is_kept(self):
        # confidence of rain => fatal is exactly 0.6
        result = run_apriori(self.tx, min_support=0.3, min_confidence=0.6)
        pairs = [(tuple(r["antecedent"]), tuple(r["consequent"]))
                 for r in result["association_rules"]]
        self.assertIn((("rain",), ("fatal",)), pairs)

    def test_two_step_api_matches_run_apriori(self):
        freq = apriori(self.tx, 0.3)
        self.assertIsInstance(next(iter(freq)), frozenset)
        self.assertAlmostEqual(freq[frozenset({"rain", "fatal"})], 0.3)
        rules = generate_rules(freq, 0.5, n_transactions=len(self.tx))
        full = run_apriori(self.tx, 0.3, 0.5)["association_rules"]
        self.assertEqual(rules, full)


class TestEdgeCases(unittest.TestCase):
    def test_float_rounding_at_support_boundary(self):
        # 0.07 * 100 == 7.000000000000001 in floating point; x occurs exactly 7x.
        tx = [{"x"}] * 7 + [{"y"}] * 93
        items = [r["items"] for r in run_apriori(tx, 0.07, 0.5)["frequent_itemsets"]]
        self.assertIn(["x"], items)

    def test_max_k_limits_size_and_none_removes_limit(self):
        tx = [{"a", "b", "c", "d", "e"}] * 5
        capped = run_apriori(tx, 0.5, 0.5, max_k=2)["metrics"]["max_itemset_size"]
        free = run_apriori(tx, 0.5, 0.5, max_k=None)["metrics"]["max_itemset_size"]
        self.assertEqual(capped, 2)
        self.assertEqual(free, 5)

    def test_bad_max_k(self):
        for bad in (0, -1, 2.5, True, "3"):
            with self.assertRaises(AprioriError):
                run_apriori([{"a"}], 0.5, 0.5, max_k=bad)

    def test_no_rules_returns_empty_list(self):
        tx = [{"a"}, {"b"}, {"c"}]
        result = run_apriori(tx, 0.3, 0.9)
        self.assertEqual(result["association_rules"], [])
        self.assertEqual(result["metrics"]["rule_count"], 0)

    def test_duplicate_and_empty_transactions(self):
        result = run_apriori([{"a", "b"}, set(), {"a", "b"}], 0.5, 0.5)
        self.assertEqual(result["metrics"]["transaction_count"], 2)

    def test_list_input_with_repeated_items_counts_once(self):
        result = run_apriori([["a", "a", "b"], ["a", "b"]], 0.5, 0.5)
        counts = {tuple(r["items"]): r["count"] for r in result["frequent_itemsets"]}
        self.assertEqual(counts[("a",)], 2)


class TestAgainstBruteForce(unittest.TestCase):
    """Compare with an obviously-correct (but slow) exhaustive counter."""

    @staticmethod
    def brute(tx, min_support, min_conf):
        n = len(tx)
        items = sorted({i for t in tx for i in t})
        freq = {}
        for k in range(1, len(items) + 1):
            for comb in combinations(items, k):
                cnt = sum(1 for t in tx if set(comb) <= t)
                if cnt / n >= min_support - 1e-9:
                    freq[frozenset(comb)] = cnt
        rules = set()
        for fs, cnt in freq.items():
            for r in range(1, len(fs)):
                for a in combinations(sorted(fs), r):
                    if cnt / freq[frozenset(a)] >= min_conf - 1e-9:
                        rules.add((tuple(sorted(a)), tuple(sorted(fs - set(a)))))
        return freq, rules

    def test_random_datasets(self):
        rng = random.Random(1)
        for _ in range(150):
            tx = [set(rng.sample("abcdefg", rng.randint(1, 6)))
                  for _ in range(rng.randint(5, 30))]
            s = rng.choice([0.1, 0.2, 0.3, 0.5])
            c = rng.choice([0.3, 0.6, 0.9])
            result = run_apriori(tx, s, c, max_k=None)
            got_sets = {frozenset(r["items"]): r["count"]
                        for r in result["frequent_itemsets"]}
            got_rules = {(tuple(r["antecedent"]), tuple(r["consequent"]))
                         for r in result["association_rules"]}
            want_sets, want_rules = self.brute(tx, s, c)
            self.assertEqual(got_sets, want_sets, (tx, s, c))
            self.assertEqual(got_rules, want_rules, (tx, s, c))


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

    def test_invariants_on_real_data(self):
        result = run_apriori(self.tx, min_support=0.05, min_confidence=0.4)
        for row in result["frequent_itemsets"]:
            self.assertGreaterEqual(row["support"], 0.05 - 1e-4)
            self.assertLessEqual(row["support"], 1.0)
            # a frequent itemset has at most one severity item
            sev = [i for i in row["items"] if i.startswith("accident_severity=")]
            self.assertLessEqual(len(sev), 1)
        self.assertTrue(result["association_rules"])
        for r in result["association_rules"]:
            self.assertGreaterEqual(r["confidence"], 0.4 - 1e-4)
            self.assertGreater(r["lift"], 0)
            self.assertFalse(set(r["antecedent"]) & set(r["consequent"]))


if __name__ == "__main__":
    unittest.main()