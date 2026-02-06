"""
Precompute a feature vector for every word.
Each word = row; each statistic = column.
"""
from __future__ import annotations

import math
from collections import Counter
import numpy as np
from typing import Any

VOWELS = set("aeiou")

# --- Letter stats ---


def length(w: str) -> int:
    return len(w)


def unique_letters(w: str) -> int:
    return len(set(w.lower()))


def vowel_ratio(w: str) -> float:
    if not w:
        return 0.0
    w = w.lower()
    return sum(1 for c in w if c in VOWELS) / len(w)


def max_letter_frequency(w: str) -> int:
    if not w:
        return 0
    return max(Counter(w.lower()).values())


def entropy(w: str) -> float:
    """Shannon entropy of letter distribution."""
    if not w:
        return 0.0
    w = w.lower()
    n = len(w)
    probs = [count / n for count in Counter(w).values()]
    return -sum(p * math.log2(p) for p in probs if p > 0)


def consonant_runs(w: str) -> int:
    """Number of maximal consonant runs."""
    if not w:
        return 0
    w = w.lower()
    runs = 0
    in_run = False
    for c in w:
        is_cons = c.isalpha() and c not in VOWELS
        if is_cons and not in_run:
            runs += 1
            in_run = True
        elif not is_cons:
            in_run = False
    return runs


def vowel_spacing_std(w: str) -> float:
    """Std of distances between consecutive vowels (in positions)."""
    w = w.lower()
    positions = [i for i, c in enumerate(w) if c in VOWELS]
    if len(positions) < 2:
        return 0.0
    gaps = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
    return float(np.std(gaps)) if len(gaps) > 1 else 0.0


def repeated_bigram_count(w: str) -> int:
    """Count of bigrams that appear more than once."""
    if len(w) < 2:
        return 0
    w = w.lower()
    bigrams = [w[i : i + 2] for i in range(len(w) - 1)]
    counts = Counter(bigrams)
    return sum(1 for c in counts.values() if c > 1)


# --- Position stats ---


def mean_letter_position(w: str) -> float:
    """Mean position in alphabet (a=0 .. z=25)."""
    if not w:
        return 0.0
    w = w.lower()
    positions = [ord(c) - ord("a") for c in w if c.isalpha()]
    return float(np.mean(positions)) if positions else 0.0


def std_letter_position(w: str) -> float:
    w = w.lower()
    positions = [ord(c) - ord("a") for c in w if c.isalpha()]
    return float(np.std(positions)) if len(positions) > 1 else 0.0


def alphabetic_order_score(w: str) -> float:
    """How much the word's letters are in alphabetical order (0 = not, 1 = fully)."""
    if len(w) < 2:
        return 1.0
    w = w.lower()
    ordered = sorted(w)
    matches = sum(1 for a, b in zip(w, ordered) if a == b)
    return matches / len(w)


# --- Language usage proxy (we don't have a real corpus; use length + entropy as proxy) ---


def corpus_frequency_proxy(w: str) -> float:
    """Proxy: shorter common-looking words get higher score. Used when no corpus loaded."""
    n = len(w)
    e = entropy(w)
    return 1.0 / (1.0 + abs(n - 5) + abs(e - 3.0))


def corpus_frequency_real(w: str, freq_map: dict[str, float]) -> float:
    """Real corpus frequency from e.g. Norvig count_1w (normalized 0–1)."""
    return freq_map.get(w.lower(), 0.0)


# --- Structural ---


def edit_density(w: str) -> float:
    """Average edit distance to other same-length words, normalized. Approx: use sum of rare bigrams."""
    if len(w) < 2:
        return 0.0
    w = w.lower()
    # Proxy: use number of rare letter pairs (both consonants, or unusual combos)
    bigrams = [w[i : i + 2] for i in range(len(w) - 1)]
    # Simple proxy: bigrams with low product of letter frequencies in English
    # ETAOIN SHRDLU order for rough frequency
    freq_rank = {c: i for i, c in enumerate("etaoinshrdlcumwfgypbvkjxqz")}
    scores = []
    for bg in bigrams:
        s = sum(freq_rank.get(c, 25) for c in bg)
        scores.append(s)
    return float(np.mean(scores)) / 25.0  # higher = weirder


def bigram_probability_proxy(w: str) -> float:
    """Proxy for 'how common are these letter pairs'. Low = weird word."""
    if len(w) < 2:
        return 0.0
    w = w.lower()
    # Use inverse of edit_density style: common letter pairs = lower score here we want "probability"
    freq_rank = {c: i for i, c in enumerate("etaoinshrdlcumwfgypbvkjxqz")}
    scores = [sum(freq_rank.get(c, 25) for c in w[i : i + 2]) for i in range(len(w) - 1)]
    # Lower sum = more common letters = higher "probability"
    return 1.0 - (np.mean(scores) / 50.0)  # rough [0,1]


# --- Feature registry (name -> function) for v1 ---

FEATURE_FUNCS = {
    "length": length,
    "unique_letters": unique_letters,
    "entropy": entropy,
    "max_letter_frequency": max_letter_frequency,
    "vowel_ratio": vowel_ratio,
    "corpus_frequency": corpus_frequency_proxy,
    "vowel_spacing_std": vowel_spacing_std,
    "alphabetic_order_score": alphabetic_order_score,
    "bigram_probability": bigram_probability_proxy,
    "edit_density": edit_density,
    "consonant_runs": consonant_runs,
}


def compute_features(word: str, freq_map: dict[str, float] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"word": word}
    for name, fn in FEATURE_FUNCS.items():
        if name == "corpus_frequency" and freq_map is not None:
            out[name] = corpus_frequency_real(word, freq_map)
        else:
            out[name] = fn(word)
    return out


def build_feature_table(words: list[str], freq_map: dict[str, float] | None = None) -> tuple[np.ndarray, list[str]]:
    """Returns structured array with 'word' and feature columns, and a list of feature names."""
    rows = [compute_features(w, freq_map) for w in words]
    # Build dtype: word as U32, then float for each metric
    max_len = max(len(r["word"]) for r in rows)
    max_len = min(max_len + 1, 32)
    dtype = [("word", f"U{max_len}")]
    feature_names = [k for k in rows[0].keys() if k != "word"]
    for k in feature_names:
        dtype.append((k, np.float64))
    arr = np.empty(len(rows), dtype=dtype)
    for i, r in enumerate(rows):
        arr[i]["word"] = r["word"][:max_len]
        for k in feature_names:
            arr[i][k] = r[k]
    return arr, feature_names
