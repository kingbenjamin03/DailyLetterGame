"""
Pattern templates: reusable rules that discover word sets from the feature table.
Each template returns one or more candidate pattern sets (list of words + hidden rule description).
"""
from __future__ import annotations

import numpy as np
from typing import NamedTuple

class CandidatePattern(NamedTuple):
    words: list[str]
    rule_description: str
    template_id: str
    metric_a: str | None
    metric_b: str | None
    percentile_used: float | None
    constraint_desc: str | None
    # For scoring
    raw_scores: dict[str, float]


def _get_column(table: np.ndarray, name: str) -> np.ndarray:
    return table[name].astype(np.float64)


def _percentile_value(arr: np.ndarray, p: float) -> float:
    return float(np.nanpercentile(arr, p))


def _z_scores(arr: np.ndarray) -> np.ndarray:
    m = np.nanmean(arr)
    s = np.nanstd(arr)
    if s == 0:
        return np.zeros_like(arr)
    return (arr - m) / s


# --- Template A: Extreme Outliers ---
# "Words that are extreme under metric X"


def template_extreme_outliers(
    table: np.ndarray,
    feature_names: list[str],
    *,
    percentile_high: float = 99.9,
    percentile_low: float = 0.1,
    min_word_length: int = 5,
    max_candidates: int = 8,
    use_high: bool = True,
) -> list[CandidatePattern]:
    """Words at the extreme (high or low) of a single metric, with length filter."""
    candidates: list[CandidatePattern] = []
    length_col = _get_column(table, "length")
    mask_len = (length_col >= min_word_length) & (length_col <= 18)

    for metric in feature_names:
        if metric == "word":
            continue
        col = _get_column(table, metric)
        valid = np.isfinite(col) & mask_len
        if valid.sum() < 20:
            continue
        vals = col[valid]
        words_subset = table["word"][valid]

        if use_high:
            thresh = _percentile_value(vals, percentile_high)
            idx = np.where(valid & (col >= thresh))[0]
            direction = "highest"
        else:
            thresh = _percentile_value(vals, percentile_low)
            idx = np.where(valid & (col <= thresh))[0]
            direction = "lowest"

        if len(idx) < 4:
            continue
        # Take up to max_candidates, spread across the tail if many
        if len(idx) > max_candidates:
            step = len(idx) / max_candidates
            idx = idx[[int(i * step) for i in range(max_candidates)]]
        words = [str(w) for w in table["word"][idx]]
        candidates.append(
            CandidatePattern(
                words=words,
                rule_description=f"Words with {direction} {metric}",
                template_id="extreme_outliers",
                metric_a=metric,
                metric_b=None,
                percentile_used=percentile_high if use_high else percentile_low,
                constraint_desc=f"length>={min_word_length}",
                raw_scores={"outlier_strength": float(np.mean(col[idx]))},
            )
        )
    return candidates


# --- Template B: Constrained Extremes ---
# "Extreme on metric X, but only among words satisfying constraint Y"


def template_constrained_extremes(
    table: np.ndarray,
    feature_names: list[str],
    *,
    constraint_metric: str = "unique_letters",
    constraint_min: float = 6,
    percentile: float = 99.0,
    min_word_length: int = 5,
    max_candidates: int = 8,
) -> list[CandidatePattern]:
    """Extreme on one metric, subject to e.g. unique_letters >= 6."""
    candidates: list[CandidatePattern] = []
    constraint_col = _get_column(table, constraint_metric)
    length_col = _get_column(table, "length")
    mask = (
        (constraint_col >= constraint_min)
        & (length_col >= min_word_length)
        & (length_col <= 18)
    )
    if mask.sum() < 30:
        return candidates

    sub_table = table[mask]
    sub_words = sub_table["word"]
    for metric in feature_names:
        if metric in ("word", constraint_metric):
            continue
        col = _get_column(sub_table, metric)
        valid = np.isfinite(col)
        if valid.sum() < 10:
            continue
        thresh = _percentile_value(col[valid], percentile)
        idx = np.where(valid & (col >= thresh))[0]
        if len(idx) < 4:
            continue
        if len(idx) > max_candidates:
            step = len(idx) / max_candidates
            idx = idx[[int(i * step) for i in range(max_candidates)]]
        words = [str(w) for w in sub_words[idx]]
        candidates.append(
            CandidatePattern(
                words=words,
                rule_description=f"Words with very high {metric} among words that have {constraint_metric} ≥ {constraint_min}",
                template_id="constrained_extremes",
                metric_a=metric,
                metric_b=constraint_metric,
                percentile_used=percentile,
                constraint_desc=f"{constraint_metric}>={constraint_min}",
                raw_scores={"outlier_strength": float(np.mean(col[idx]))},
            )
        )
    return candidates


# --- Template C: Ratio Anomalies ---
# "Words where two metrics behave oddly together"


def template_ratio_anomalies(
    table: np.ndarray,
    feature_names: list[str],
    *,
    min_word_length: int = 5,
    max_candidates: int = 8,
    z_threshold: float = 2.0,
) -> list[CandidatePattern]:
    """E.g. long words with very few unique letters; short words with high entropy."""
    candidates: list[CandidatePattern] = []
    length_col = _get_column(table, "length")
    mask = (length_col >= min_word_length) & (length_col <= 18)
    if mask.sum() < 50:
        return candidates

    # Pairs that are interesting: (metric_a, metric_b) where we want one high and one low
    pairs = [
        ("length", "unique_letters"),   # long but few unique letters
        ("length", "entropy"),          # long but low entropy
        ("length", "max_letter_frequency"),  # long but one letter dominates
        ("entropy", "length"),          # high entropy but short
        ("vowel_ratio", "consonant_runs"),   # odd vowel/consonant structure
    ]
    # Filter to existing columns
    available = set(feature_names)
    for ma, mb in pairs:
        if ma not in available or mb not in available:
            continue
        col_a = _get_column(table, ma)
        col_b = _get_column(table, mb)
        valid = mask & np.isfinite(col_a) & np.isfinite(col_b)
        if valid.sum() < 20:
            continue
        # Z-scores within valid slice
        za = _z_scores(col_a[valid])
        zb = _z_scores(col_b[valid])
        # Anomaly: high A and low B (or vice versa)
        # score = za - zb  => high when A high, B low
        combo = za - zb
        thresh = _percentile_value(combo, 99.0)
        idx_in_sub = np.where(combo >= thresh)[0]
        idx_full = np.where(valid)[0][idx_in_sub]
        if len(idx_full) < 4:
            continue
        if len(idx_full) > max_candidates:
            step = len(idx_full) / max_candidates
            idx_full = idx_full[[int(i * step) for i in range(max_candidates)]]
        words = [str(w) for w in table["word"][idx_full]]
        candidates.append(
            CandidatePattern(
                words=words,
                rule_description=f"Words with unusually high {ma} and low {mb} (ratio anomaly)",
                template_id="ratio_anomaly",
                metric_a=ma,
                metric_b=mb,
                percentile_used=99.0,
                constraint_desc=None,
                raw_scores={"combo_z": float(np.mean(combo[idx_in_sub[: len(words)]]))},
            )
        )
    return candidates


def run_all_templates(
    table: np.ndarray,
    feature_names: list[str],
    *,
    max_per_template: int = 30,
) -> list[CandidatePattern]:
    """Run all v1 templates and return a combined list of candidates."""
    out: list[CandidatePattern] = []
    out.extend(
        template_extreme_outliers(table, feature_names, use_high=True)[:max_per_template]
    )
    out.extend(
        template_extreme_outliers(table, feature_names, use_high=False)[:max_per_template]
    )
    out.extend(
        template_constrained_extremes(table, feature_names)[:max_per_template]
    )
    out.extend(template_ratio_anomalies(table, feature_names)[:max_per_template])
    return out
