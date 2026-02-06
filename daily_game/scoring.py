"""
Pattern Quality Score (PQS):
  outlier_strength + internal_coherence + human_guessability - obscurity_penalty
"""
from __future__ import annotations

import numpy as np
from .patterns import CandidatePattern


def _outlier_strength(candidate: CandidatePattern, table: np.ndarray) -> float:
    """Z-score or percentile distance of the selected words vs rest of corpus."""
    if not candidate.words or candidate.metric_a is None:
        return 0.0
    col = table[candidate.metric_a].astype(np.float64)
    valid = np.isfinite(col)
    if valid.sum() < 10:
        return 0.0
    mean_all = np.mean(col[valid])
    std_all = np.std(col[valid])
    if std_all == 0:
        return 0.0
    word_set = set(candidate.words)
    mask_sel = np.array([w in word_set for w in table["word"]])
    if mask_sel.sum() == 0:
        return 0.0
    mean_sel = np.mean(col[mask_sel])
    return float(abs(mean_sel - mean_all) / std_all)


def _internal_coherence(candidate: CandidatePattern, table: np.ndarray) -> float:
    """Low variance within selected words on the primary metric => higher score."""
    if not candidate.words or candidate.metric_a is None:
        return 0.0
    word_set = set(candidate.words)
    mask = np.array([w in word_set for w in table["word"]])
    col = table[candidate.metric_a].astype(np.float64)[mask]
    if len(col) < 2:
        return 1.0
    std_sel = np.std(col)
    std_all = np.nanstd(table[candidate.metric_a].astype(np.float64))
    if std_all == 0:
        return 1.0
    # Coherent = low variance relative to full distribution
    return max(0.0, 1.0 - (std_sel / std_all))


def _human_guessability(candidate: CandidatePattern) -> float:
    """Favor patterns where words are recognizable (length, no ultra-rare)."""
    if not candidate.words:
        return 0.0
    lens = [len(w) for w in candidate.words]
    mean_len = sum(lens) / len(lens)
    # Sweet spot: 4–10 letters
    if 4 <= mean_len <= 10:
        len_score = 1.0
    elif 3 <= mean_len <= 12:
        len_score = 0.7
    else:
        len_score = 0.4
    # Penalize if any word is very long or very short
    weird = sum(1 for l in lens if l < 3 or l > 14)
    weird_penalty = weird / max(len(lens), 1)
    return max(0.0, len_score - weird_penalty * 0.3)


def _obscurity_penalty(candidate: CandidatePattern) -> float:
    """Penalize if words look obscure (very long, lots of rare letters)."""
    if not candidate.words:
        return 0.0
    penalty = 0.0
    for w in candidate.words:
        if len(w) > 12:
            penalty += 0.2
        # Rare letters
        rare = sum(1 for c in w if c in "jqxzkv")
        penalty += 0.05 * (rare / max(len(w), 1))
    return min(1.0, penalty / len(candidate.words))


def pqs(candidate: CandidatePattern, table: np.ndarray) -> float:
    """
    Pattern Quality Score. Higher = better pattern.
    Scale is roughly 0–4; we use threshold ~1.0–1.5 for "publishable".
    """
    o = _outlier_strength(candidate, table)
    c = _internal_coherence(candidate, table)
    g = _human_guessability(candidate)
    ob = _obscurity_penalty(candidate)
    return o * 0.4 + c * 0.3 + g * 0.4 - ob * 0.5


def filter_and_rank(
    candidates: list[CandidatePattern],
    table: np.ndarray,
    *,
    min_pqs: float = 0.8,
    min_words: int = 4,
    max_words: int = 12,
) -> list[tuple[CandidatePattern, float]]:
    """Return (candidate, pqs) sorted by pqs descending, above min_pqs and word count in range."""
    scored: list[tuple[CandidatePattern, float]] = []
    for c in candidates:
        if not (min_words <= len(c.words) <= max_words):
            continue
        s = pqs(c, table)
        if s >= min_pqs:
            scored.append((c, s))
    scored.sort(key=lambda x: -x[1])
    return scored


def difficulty_from_pqs(pqs_score: float) -> str:
    """easy / medium / hard from PQS band."""
    if pqs_score >= 2.2:
        return "easy"
    if pqs_score >= 1.4:
        return "medium"
    return "hard"
