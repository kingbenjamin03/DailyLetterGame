"""
Real corpus frequency from Norvig's count_1w.txt (Google 1T word corpus).
Download on first use and cache to data/count_1w.txt.
"""
from __future__ import annotations

import logging
import math
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COUNT_1W_URL = "https://norvig.com/ngrams/count_1w.txt"
COUNT_1W_PATH = DATA_DIR / "count_1w.txt"


def ensure_count_1w() -> Path:
    """Download count_1w.txt if missing. Returns path to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if COUNT_1W_PATH.exists():
        return COUNT_1W_PATH
    try:
        logging.info("Downloading %s ...", COUNT_1W_URL)
        urllib.request.urlretrieve(COUNT_1W_URL, COUNT_1W_PATH)
        return COUNT_1W_PATH
    except Exception as e:
        raise FileNotFoundError(
            f"Could not download {COUNT_1W_URL}. "
            f"Download manually to {COUNT_1W_PATH} (word TAB count per line). Error: {e}"
        ) from e


def load_frequency_map(path: Path | None = None) -> dict[str, float]:
    """
    Load word -> log10(count+1) for corpus frequency feature.
    Normalized so that common words are in a reasonable range.
    """
    p = path or ensure_count_1w()
    if not p.exists():
        return {}
    freqs: dict[str, float] = {}
    total = 0.0
    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 2:
                continue
            word, count_str = parts[0].lower().strip(), parts[1].strip()
            try:
                count = int(count_str)
            except ValueError:
                continue
            if not word.isalpha():
                continue
            freqs[word] = float(count)
            total += count
    if not total:
        return freqs
    # Normalize to log scale, max around 1.0 for the commonest word
    max_count = max(freqs.values()) if freqs else 1
    for w, c in freqs.items():
        freqs[w] = (1.0 + math.log10(c + 1)) / (1.0 + math.log10(max_count + 1))
    return freqs
