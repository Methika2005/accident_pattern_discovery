"""
apriori.py  --  Association-rule mining (Apriori, implemented from scratch)
===========================================================================

Public interface
----------------
    apriori(transactions, min_support, max_k=4)
        -> dict[frozenset[str], float]
        Frequent itemsets mapped to their support (a fraction in (0, 1]).

    generate_rules(frequent_itemsets, min_confidence, n_transactions=None)
        -> list[dict]
        Association rules with support, confidence and lift, built from the
        output of apriori().

    run_apriori(transactions, min_support, min_confidence, max_k=4) -> dict
        Used by Member 3 / Flask.  Runs both steps and returns a
        JSON-serialisable dict with frequent_itemsets, association_rules and
        metrics.

    AprioriError  --  ValueError raised on invalid thresholds / empty input

Definitions
-----------
    support(X)        = count(X) / N
    confidence(A=>C)  = support(A u C) / support(A)
    lift(A=>C)        = confidence(A=>C) / support(C)

max_k limits the largest itemset size that is searched.  Pass max_k=None to
search without a limit (the loop then stops by itself when no candidate
survives).  The default of 4 keeps responses small and fast.
"""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import combinations
from time import perf_counter
from typing import Iterable, Mapping, Sequence

DEFAULT_MAX_K = 4

# Tolerance for comparing floating-point confidence against the threshold,
# so a rule with confidence exactly 0.6 is not lost to 0.5999999999.
_EPS = 1e-9


class AprioriError(ValueError):
    """Raised when mining cannot run because the input is invalid."""


def _validate_fraction(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AprioriError(f"{name} must be a number between 0 and 1.")
    value = float(value)
    if value <= 0 or value > 1:
        raise AprioriError(f"{name} must be > 0 and <= 1 (got {value}).")
    return value


def _validate_max_k(max_k):
    """None means 'no limit'; otherwise a positive integer."""
    if max_k is None:
        return None
    if isinstance(max_k, bool) or not isinstance(max_k, int) or max_k < 1:
        raise AprioriError("max_k must be a positive integer or None.")
    return max_k


def _min_count(min_support: float, n: int) -> int:
    """
    Smallest integer count that satisfies support >= min_support.

    Plain `min_support * n` is a float: 0.07 * 100 == 7.000000000000001, which
    would wrongly reject an itemset that occurs in exactly 7 of 100
    transactions.  Rounding to 9 places first removes that noise.
    """
    return max(1, math.ceil(round(min_support * n, 9)))


# ---------------------------------------------------------------------------
# Candidate generation and counting
# ---------------------------------------------------------------------------
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
            # Prune: every (k-1)-subset must itself be frequent.
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


def _mine_counts(
    transactions: Sequence[Iterable[str]],
    min_support: float,
    max_k: int | None,
):
    """
    Core Apriori loop.

    Returns (support_counts, n, id_to_item) where support_counts maps a sorted
    tuple of integer item ids to its absolute count.  Empty transactions are
    ignored, and n is the number of non-empty transactions.
    """
    item_to_id: dict[str, int] = {}
    id_to_item: list[str] = []
    encoded: list[tuple[int, ...]] = []
    for raw in transactions:
        ids: set[int] = set()
        for item in raw:
            if item not in item_to_id:
                item_to_id[item] = len(id_to_item)
                id_to_item.append(str(item))
            ids.add(item_to_id[item])
        if ids:
            encoded.append(tuple(sorted(ids)))

    n = len(encoded)
    if n == 0:
        raise AprioriError("No transactions to mine.")
    min_count = _min_count(min_support, n)

    # L1: frequent single items
    l1_counts: dict[int, int] = defaultdict(int)
    for txn in encoded:
        for item in txn:
            l1_counts[item] += 1

    support_counts: dict[tuple[int, ...], int] = {}
    current: list[tuple[int, ...]] = []
    for item, count in l1_counts.items():
        if count >= min_count:
            support_counts[(item,)] = count
            current.append((item,))

    # L2, L3, ... until nothing survives (or max_k is reached)
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

    return support_counts, n, id_to_item


def _to_supports(
    support_counts: Mapping[tuple[int, ...], int],
    n: int,
    id_to_item: Sequence[str],
) -> dict[frozenset, float]:
    """Convert id-tuple counts to {frozenset of item strings: support}."""
    return {
        frozenset(id_to_item[i] for i in itemset): count / n
        for itemset, count in support_counts.items()
    }


# ---------------------------------------------------------------------------
# Public step 1: frequent itemsets
# ---------------------------------------------------------------------------
def apriori(
    transactions: Iterable[Iterable[str]],
    min_support: float,
    max_k: int | None = DEFAULT_MAX_K,
) -> dict[frozenset, float]:
    """
    Find all frequent itemsets.

    Returns {frozenset_of_items: support}, support as an unrounded fraction.
    """
    min_support = _validate_fraction("min_support", min_support)
    max_k = _validate_max_k(max_k)
    support_counts, n, id_to_item = _mine_counts(transactions, min_support, max_k)
    return _to_supports(support_counts, n, id_to_item)


# ---------------------------------------------------------------------------
# Public step 2: association rules
# ---------------------------------------------------------------------------
def generate_rules(
    frequent_itemsets: Mapping[frozenset, float],
    min_confidence: float,
    n_transactions: int | None = None,
) -> list[dict]:
    """
    Build rules A => C from frequent itemsets.

    frequent_itemsets : output of apriori()
    n_transactions    : if given, each rule also reports an absolute `count`

    Every subset of a frequent itemset is frequent too (Apriori property), so
    for output of apriori() the supports of A and C are always present.
    """
    min_confidence = _validate_fraction("min_confidence", min_confidence)
    rules: list[dict] = []
    for itemset, union_support in frequent_itemsets.items():
        if len(itemset) < 2:
            continue
        items = sorted(itemset)
        for r in range(1, len(items)):
            for ant in combinations(items, r):
                antecedent = frozenset(ant)
                consequent = itemset - antecedent
                ant_support = frequent_itemsets.get(antecedent)
                cons_support = frequent_itemsets.get(consequent)
                if not ant_support or not cons_support:
                    continue  # only for hand-built input missing a subset
                confidence = union_support / ant_support
                if confidence + _EPS < min_confidence:
                    continue
                rule = {
                    "antecedent": sorted(antecedent),
                    "consequent": sorted(consequent),
                    "support": round(union_support, 4),
                    "confidence": round(confidence, 4),
                    "lift": round(confidence / cons_support, 4),
                    "antecedent_support": round(ant_support, 4),
                    "consequent_support": round(cons_support, 4),
                }
                if n_transactions:
                    rule["count"] = int(round(union_support * n_transactions))
                rules.append(rule)

    rules.sort(key=lambda r: (-r["lift"], -r["confidence"], -r["support"],
                              r["antecedent"], r["consequent"]))
    return rules


# ---------------------------------------------------------------------------
# Convenience wrapper used by Flask
# ---------------------------------------------------------------------------
def run_apriori(
    transactions: Iterable[Iterable[str]],
    min_support: float,
    min_confidence: float,
    max_k: int | None = DEFAULT_MAX_K,
) -> dict:
    """
    Mine frequent itemsets and association rules.

    Itemsets and rule sides are sorted lists of item strings so the result can
    be passed straight to flask.jsonify.
    """
    min_support = _validate_fraction("min_support", min_support)
    min_confidence = _validate_fraction("min_confidence", min_confidence)
    max_k = _validate_max_k(max_k)

    started = perf_counter()
    support_counts, n, id_to_item = _mine_counts(transactions, min_support, max_k)

    frequent_itemsets = [
        {
            "items": _decode(itemset, id_to_item),
            "size": len(itemset),
            "count": int(count),
            "support": round(count / n, 4),
        }
        for itemset, count in sorted(
            support_counts.items(),
            key=lambda kv: (len(kv[0]), -kv[1], _decode(kv[0], id_to_item)),
        )
    ]

    association_rules = generate_rules(
        _to_supports(support_counts, n, id_to_item),
        min_confidence,
        n_transactions=n,
    )

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
            "elapsed_seconds": round(perf_counter() - started, 4),
        },
    }