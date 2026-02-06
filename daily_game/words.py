"""
Load and filter word list for the feature universe.
Uses system dict (e.g. /usr/share/dict/words) or env WORD_LIST path.
"""
from pathlib import Path
import os
import re

# Default: system word list on macOS/Unix
DEFAULT_WORD_LIST = Path("/usr/share/dict/words")
MIN_LENGTH = 3
MAX_LENGTH = 20
# Only alphabetic; no proper-noun-only lists for now
ALPHA_ONLY = re.compile(r"^[a-zA-Z]+$")


def get_word_list_path() -> Path:
    p = os.environ.get("WORD_LIST")
    if p:
        return Path(p)
    if DEFAULT_WORD_LIST.exists():
        return DEFAULT_WORD_LIST
    raise FileNotFoundError(
        "No word list found. Set WORD_LIST to a path or install system dict (e.g. /usr/share/dict/words)."
    )


def load_words(
    *,
    min_length: int = MIN_LENGTH,
    max_length: int = MAX_LENGTH,
    alpha_only: bool = True,
    lower: bool = True,
) -> list[str]:
    path = get_word_list_path()
    words: list[str] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            w = line.strip()
            if lower:
                w = w.lower()
            if not w or w in seen:
                continue
            if alpha_only and not ALPHA_ONLY.match(w):
                continue
            if min_length <= len(w) <= max_length:
                words.append(w)
                seen.add(w)
    return words
