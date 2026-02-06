"""
Daily pattern generator: load feature table, run templates, score, pick best, avoid repeats.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np

from .patterns import run_all_templates, CandidatePattern
from .scoring import filter_and_rank, difficulty_from_pqs
from .hints import generate_hints

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
FEATURE_TABLE_PATH = DATA_DIR / "feature_table.npz"
USED_PATTERNS_PATH = DATA_DIR / "used_patterns.json"
TODAY_JSON_PATH = DATA_DIR / "today.json"
MAX_CANDIDATES_TO_GENERATE = 150
MIN_PQS = 0.7
NO_REUSE_DAYS = 30
MAX_WORD_REUSE_PER_MONTH = 2


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def load_feature_table() -> tuple[np.ndarray, list[str]]:
    """Load cached feature table. Raises if not built."""
    if not FEATURE_TABLE_PATH.exists():
        raise FileNotFoundError(
            f"Feature table not found at {FEATURE_TABLE_PATH}. Run: python -m daily_game.build_features"
        )
    data = np.load(FEATURE_TABLE_PATH, allow_pickle=True)
    table = data["table"]
    fn = data["feature_names"]
    feature_names = fn.tolist() if hasattr(fn, "tolist") else list(fn)
    return table, feature_names


def load_used_patterns() -> list[dict]:
    if not USED_PATTERNS_PATH.exists():
        return []
    with open(USED_PATTERNS_PATH, "r") as f:
        return json.load(f)


def save_used_pattern(pattern: CandidatePattern, pqs_score: float) -> None:
    ensure_data_dir()
    used = load_used_patterns()
    used.append({
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "rule": pattern.rule_description,
        "template_id": pattern.template_id,
        "metric_a": pattern.metric_a,
        "metric_b": pattern.metric_b,
        "constraint_desc": pattern.constraint_desc,
        "words": pattern.words,
        "pqs": pqs_score,
    })
    with open(USED_PATTERNS_PATH, "w") as f:
        json.dump(used, f, indent=2)


def _pattern_signature(p: CandidatePattern) -> str:
    """Unique enough key for deduping metric combos."""
    return f"{p.template_id}|{p.metric_a}|{p.metric_b or ''}|{p.constraint_desc or ''}"


def _recent_signatures(used: list[dict], within_days: int = NO_REUSE_DAYS) -> set[str]:
    cutoff = (datetime.utcnow() - timedelta(days=within_days)).strftime("%Y-%m-%d")
    sigs = set()
    for u in used:
        if u.get("date", "") >= cutoff:
            sigs.add(
                f"{u.get('template_id','')}|{u.get('metric_a','')}|{u.get('metric_b') or ''}|{u.get('constraint_desc') or ''}"
            )
    return sigs


def _word_use_counts(used: list[dict], within_days: int = 31) -> dict[str, int]:
    cutoff = (datetime.utcnow() - timedelta(days=within_days)).strftime("%Y-%m-%d")
    counts: dict[str, int] = {}
    for u in used:
        if u.get("date", "") >= cutoff:
            for w in u.get("words", []):
                counts[w] = counts.get(w, 0) + 1
    return counts


def select_best_pattern(
    table: np.ndarray,
    feature_names: list[str],
    *,
    skip_recent_metric_combos: bool = True,
    skip_overused_words: bool = True,
) -> tuple[CandidatePattern, float] | None:
    """Generate candidates, score, filter by recency, return best or None."""
    candidates = run_all_templates(
        table, feature_names, max_per_template=40
    )
    scored = filter_and_rank(
        candidates, table, min_pqs=MIN_PQS, min_words=4, max_words=10
    )
    if not scored:
        return None

    used = load_used_patterns()
    recent_sigs = _recent_signatures(used, NO_REUSE_DAYS) if skip_recent_metric_combos else set()
    word_counts = _word_use_counts(used) if skip_overused_words else {}

    for candidate, pqs_score in scored:
        sig = _pattern_signature(candidate)
        if sig in recent_sigs:
            continue
        if skip_overused_words:
            overused = [w for w in candidate.words if word_counts.get(w, 0) >= MAX_WORD_REUSE_PER_MONTH]
            if overused:
                continue
        return candidate, pqs_score
    return None


def load_today() -> dict | None:
    """Load today's puzzle from data/today.json if it exists and is for today."""
    if not TODAY_JSON_PATH.exists():
        return None
    try:
        with open(TODAY_JSON_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    if data.get("date") != today_str:
        return None
    return data


def ensure_today_puzzle() -> dict | None:
    """Ensure today's puzzle exists: load from file or generate. Returns puzzle dict or None."""
    data = load_today()
    if data is not None:
        return data
    return generate_daily()


def _write_today_json(pattern: CandidatePattern, pqs_score: float) -> None:
    """Write today's puzzle to data/today.json for the frontend."""
    ensure_data_dir()
    hints = generate_hints(pattern)
    difficulty = difficulty_from_pqs(pqs_score)
    payload = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "words": pattern.words,
        "hints": hints,
        "rule": pattern.rule_description,
        "difficulty": difficulty,
        "pqs": round(pqs_score, 2),
        "metric_a": pattern.metric_a,
    }
    with open(TODAY_JSON_PATH, "w") as f:
        json.dump(payload, f, indent=2)


def generate_daily() -> dict | None:
    """
    Load table, pick best pattern, record it, write today.json, return dict for display.
    Returns None if no valid pattern found.
    """
    table, feature_names = load_feature_table()
    result = select_best_pattern(table, feature_names)
    if result is None:
        return None
    pattern, pqs_score = result
    save_used_pattern(pattern, pqs_score)
    _write_today_json(pattern, pqs_score)
    return {
        **_puzzle_dict(pattern, pqs_score),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def _puzzle_dict(pattern: CandidatePattern, pqs_score: float) -> dict:
    """Build the puzzle payload dict (no persistence)."""
    return {
        "words": pattern.words,
        "rule": pattern.rule_description,
        "template_id": pattern.template_id,
        "pqs": round(pqs_score, 2),
        "difficulty": difficulty_from_pqs(pqs_score),
        "hints": generate_hints(pattern),
        "metric_a": pattern.metric_a,
    }


def _get_scored_candidates(
    table: np.ndarray,
    feature_names: list[str],
    *,
    skip_recent: bool = False,
    skip_overused: bool = False,
) -> list[tuple[CandidatePattern, float]]:
    """Return list of (pattern, score) that pass filters. For random we use skip_*=False so pool is large."""
    candidates = run_all_templates(table, feature_names, max_per_template=40)
    scored = filter_and_rank(candidates, table, min_pqs=MIN_PQS, min_words=4, max_words=10)
    if not scored:
        return []
    used = load_used_patterns()
    recent_sigs = _recent_signatures(used, NO_REUSE_DAYS) if skip_recent else set()
    word_counts = _word_use_counts(used) if skip_overused else {}
    out = []
    for candidate, pqs_score in scored:
        sig = _pattern_signature(candidate)
        if sig in recent_sigs:
            continue
        if skip_overused:
            overused = [w for w in candidate.words if word_counts.get(w, 0) >= MAX_WORD_REUSE_PER_MONTH]
            if overused:
                continue
        out.append((candidate, pqs_score))
    return out


def generate_random_puzzle() -> dict | None:
    """
    Generate a one-off puzzle with a different topic (no save to today.json or used_patterns).
    Randomly picks from the full pool of valid patterns so each "New puzzle" is different.
    """
    table, feature_names = load_feature_table()
    pool = _get_scored_candidates(
        table, feature_names,
        skip_recent=False,
        skip_overused=False,
    )
    if not pool:
        return None
    pattern, pqs_score = random.choice(pool)
    return _puzzle_dict(pattern, pqs_score)
