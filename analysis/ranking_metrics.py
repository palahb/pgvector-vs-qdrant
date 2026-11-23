"""Ranking metrics for E23. Gains are the TREC grades themselves (linear gain), a discount of
1/log2(rank + 1), and the ideal ranking is taken from the relevant items that exist in the corpus
being searched (here the 1M-passage prefix), not from the whole collection."""

from __future__ import annotations

import math
from typing import Sequence


def dcg(grades: Sequence[int], k: int) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(grades[:k]))


def ndcg_at_k(ranked: Sequence[int], available: Sequence[int], k: int) -> float | None:
    """`ranked`: grades of the returned items in rank order. `available`: grades of every item of the corpus
    that has a judgment. None when the corpus holds nothing relevant."""
    ideal = dcg(sorted(available, reverse=True), k)
    if ideal <= 0:
        return None
    return dcg(ranked, k) / ideal


def mrr_at_k(ranked: Sequence[int], k: int, threshold: int = 2) -> float:
    for i, g in enumerate(ranked[:k]):
        if g >= threshold:
            return 1.0 / (i + 1)
    return 0.0


def recall_at_k(ranked: Sequence[int], relevant_available: int, k: int, threshold: int = 2) -> float | None:
    if relevant_available <= 0:
        return None
    found = sum(1 for g in ranked[:k] if g >= threshold)
    return found / min(k, relevant_available)
