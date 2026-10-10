"""
apriori.py  --  Association-rule mining (Apriori)
================================================

Public interface (used by Member 3 / Flask)
------------------------------------------
    run_apriori(transactions, min_support, min_confidence) -> dict

        transactions     : list[set[str]]  (or frozenset)
        min_support      : float in (0, 1]
        min_confidence   : float in (0, 1]

        Returns a JSON-serialisable dict with frequent_itemsets,
        association_rules, and metrics.

    AprioriError  --  ValueError raised on invalid thresholds / empty input
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from time import perf_counter
from typing import Iterable, Mapping, Sequence


class AprioriError(ValueError):
    """Raised when mining cannot run because the input is invalid."""


def _validate_fraction(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AprioriError(f"{name} must be a number between 0 and 1.")
    value = float(value)
    if value <= 0 or value > 1:
        raise AprioriError(f"{name} must be > 0 and <= 1 (got {value}).")
    return value


def _generate_candidates(prev: Sequence[tuple[int, ...]], k: int) -> list[tuple[int, ...]]:
    """Apriori join + prune: L_{k-1} x L_{k-1} -> C_k."""
    prev_sorted = sorted(prev)
    prev_set = set(prev_sorted)
    candidates: list[tuple[int, ...]] = []
    n = len(prev_sorted)
    prefix_len = k - 2
    for i in range(n):
        a = prev_sorted[i]
        for j in range(i + 1, n):
            b = prev_sorted[j]
            if a[:prefix_len] != b[:prefix_len]:
                break
            cand = a + (b[-1],)
            if prefix_len == 0 or all(
                subset in prev_set for subset in combinations(cand, k - 1)
            ):
                candidates.append(cand)
    return candidates


def _count_candidates(
    encoded: Sequence[Sequence[int]],
    candidates: Sequence[tuple[int, ...]],
    k: int,
) -> dict[tuple[int, ...], int]:
    cand_set = set(candidates)
    counts: dict[tuple[int, ...], int] = defaultdict(int)
    n_cand = len(cand_set)
    for txn in encoded:
        if len(txn) < k:
            continue
        if n_cand <= 64:
            tset = set(txn)
            for cand in cand_set:
                if tset.issuperset(cand):
                    counts[cand] += 1
        else:
            for subset in combinations(txn, k):
                if subset in cand_set:
                    counts[subset] += 1
    return counts


def _decode(itemset: Iterable[int], id_to_item: Sequence[str]) -> list[str]:
    return sorted(id_to_item[i] for i in itemset)


def run_apriori(
    transactions: Sequence[Iterable[str]],
    min_support: float,
    min_confidence: float,
    max_k: int | None = 4,
) -> dict:
    """
    Mine frequent itemsets and association rules with Apriori.

    Itemsets and rule sides are sorted lists of item strings so the result
    can be passed straight to flask.jsonify.
    """
    min_support = _validate_fraction("min_support", min_support)
    min_confidence = _validate_fraction("min_confidence", min_confidence)
    if max_k is None:
        max_k = 4
    if not isinstance(max_k, int) or isinstance(max_k, bool) or max_k < 1:
        raise AprioriError("max_k must be a positive integer.")

    started = perf_counter()
    n = len(transactions)
    if n == 0:
        raise AprioriError("No transactions to mine.")

    min_count = min_support * n  # keep as float so 0.1494 * 20000 still works

    item_to_id: dict[str, int] = {}
    id_to_item: list[str] = []
    encoded: list[tuple[int, ...]] = []
    for raw in transactions:
        ids: list[int] = []
        seen: set[int] = set()
        for item in raw:
            if item not in item_to_id:
                item_to_id[item] = len(id_to_item)
                id_to_item.append(str(item))
            idx = item_to_id[item]
            if idx not in seen:
                seen.add(idx)
                ids.append(idx)
        if ids:
            encoded.append(tuple(sorted(ids)))

    n = len(encoded)
    if n == 0:
        raise AprioriError("No transactions to mine.")
    min_count = min_support * n

    # --- L1 ---------------------------------------------------------------
    l1_counts: dict[int, int] = defaultdict(int)
    for txn in encoded:
        for item in txn:
            l1_counts[item] += 1

    support_counts: dict[tuple[int, ...], int] = {}
    current: list[tuple[int, ...]] = []
    for item, count in l1_counts.items():
        if count >= min_count:
            key = (item,)
            support_counts[key] = count
            current.append(key)

    k = 2
    while current and (max_k is None or k <= max_k):
        candidates = _generate_candidates(current, k)
        if not candidates:
            break
        counts = _count_candidates(encoded, candidates, k)
        nxt: list[tuple[int, ...]] = []
        for cand, count in counts.items():
            if count >= min_count:
                support_counts[cand] = count
                nxt.append(cand)
        current = nxt
        k += 1

    frequent_itemsets = []
    for itemset, count in sorted(
        support_counts.items(),
        key=lambda kv: (len(kv[0]), -kv[1], _decode(kv[0], id_to_item)),
    ):
        frequent_itemsets.append({
            "items": _decode(itemset, id_to_item),
            "size": len(itemset),
            "count": int(count),
            "support": round(count / n, 4),
        })

    association_rules = _build_rules(
        support_counts, n, min_confidence, id_to_item
    )

    elapsed = round(perf_counter() - started, 4)
    max_size = max((len(s) for s in support_counts), default=0)
    return {
        "frequent_itemsets": frequent_itemsets,
        "association_rules": association_rules,
        "metrics": {
            "min_support": min_support,
            "min_confidence": min_confidence,
            "transaction_count": n,
            "distinct_item_count": len(id_to_item),
            "frequent_itemset_count": len(frequent_itemsets),
            "rule_count": len(association_rules),
            "max_itemset_size": max_size,
            "max_k": max_k,
            "elapsed_seconds": elapsed,
        },
    }


def _build_rules(
    support_counts: Mapping[tuple[int, ...], int],
    n: int,
    min_confidence: float,
    id_to_item: Sequence[str],
) -> list[dict]:
    rules: list[dict] = []
    for itemset, union_count in support_counts.items():
        if len(itemset) < 2:
            continue
        union_support = union_count / n
        k = len(itemset)
        for r in range(1, k):
            for antecedent in combinations(itemset, r):
                antecedent = tuple(sorted(antecedent))
                ant_count = support_counts.get(antecedent)
                if not ant_count:
                    continue
                consequent = tuple(sorted(set(itemset) - set(antecedent)))
                cons_count = support_counts.get(consequent)
                if not cons_count:
                    continue
                confidence = union_count / ant_count
                if confidence < min_confidence:
                    continue
                cons_support = cons_count / n
                lift = confidence / cons_support if cons_support else 0.0
                rules.append({
                    "antecedent": _decode(antecedent, id_to_item),
                    "consequent": _decode(consequent, id_to_item),
                    "support": round(union_support, 4),
                    "confidence": round(confidence, 4),
                    "lift": round(lift, 4),
                    "antecedent_support": round(ant_count / n, 4),
                    "consequent_support": round(cons_support, 4),
                    "count": int(union_count),
                })

    rules.sort(key=lambda r: (-r["lift"], -r["confidence"], -r["support"],
                              r["antecedent"], r["consequent"]))
    return rules
