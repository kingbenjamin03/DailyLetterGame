"""
Build and cache the feature table from the word list.
Run once (or when word list changes): python -m daily_game.build_features
Uses real corpus frequency from Norvig count_1w if available (downloads on first run).
"""
import numpy as np

from .words import load_words
from .features import build_feature_table
from .generator import ensure_data_dir, FEATURE_TABLE_PATH


def main() -> None:
    print("Loading words...")
    words = load_words()
    print(f"  {len(words)} words")

    freq_map = {}
    try:
        from .corpus import load_frequency_map, ensure_count_1w
        ensure_count_1w()
        freq_map = load_frequency_map()
        print(f"  Corpus frequency: {len(freq_map)} words from count_1w")
    except Exception as e:
        print(f"  Corpus frequency: using proxy ({e})")

    print("Computing features...")
    table, feature_names = build_feature_table(words, freq_map=freq_map if freq_map else None)
    print(f"  Table shape: {table.shape}, features: {feature_names}")

    ensure_data_dir()
    np.savez(
        FEATURE_TABLE_PATH,
        table=table,
        feature_names=feature_names,
    )
    print(f"Saved to {FEATURE_TABLE_PATH}")


if __name__ == "__main__":
    main()
