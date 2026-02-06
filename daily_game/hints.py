"""
Generate 3 user-facing hints for a pattern (easy → hard).
Each hint is tied to the actual rule and gets more specific.
"""
from __future__ import annotations

from .patterns import CandidatePattern

# For each metric: [hint 1 = concept, hint 2 = more specific, hint 3 = almost the rule]
# Hints must be about the SAME idea so they feel coherent.
METRIC_HINTS = {
    "length": [
        "The pattern is about how long the words are.",
        "These words are similar in their number of letters.",
        "They all have an unusual word length compared to most English words.",
    ],
    "unique_letters": [
        "The pattern is about how many different letters appear in each word.",
        "Count the distinct letters in each word.",
        "These words have an unusual number of unique letters (either very few or very many).",
    ],
    "entropy": [
        "The pattern is about letter repetition and variety.",
        "Some letters repeat a lot in these words, or they're very mixed — the rule picks one extreme.",
        "They share an extreme in how predictable or random their letter distribution is.",
    ],
    "max_letter_frequency": [
        "The pattern is about one letter repeating a lot in each word.",
        "In each word, a single letter appears much more often than the others.",
        "These words have an unusually high (or low) “most repeated letter” count.",
    ],
    "vowel_ratio": [
        "The pattern is about vowels vs consonants.",
        "Look at the proportion of vowels in each word.",
        "These words have an unusual ratio of vowels to consonants.",
    ],
    "corpus_frequency": [
        "The pattern is about how common or rare these words are in real English.",
        "Think about how often you'd see these words in books or speech.",
        "These words are similar in how frequently they appear in the language.",
    ],
    "vowel_spacing_std": [
        "The pattern is about where vowels sit in the word.",
        "Look at the spacing or gaps between consecutive vowels.",
        "These words have unusually even or uneven spacing between their vowels.",
    ],
    "alphabetic_order_score": [
        "The pattern is about the order of letters in the alphabet.",
        "Look at whether the letters in each word follow A–Z order.",
        "These words have letters that are unusually close to (or far from) alphabetical order.",
    ],
    "bigram_probability": [
        "The pattern is about two-letter combinations.",
        "Think about how common or rare the letter pairs in these words are.",
        "These words have unusually common (or rare) two-letter sequences.",
    ],
    "edit_density": [
        "The pattern is about how unusual the letter combinations are.",
        "Think about rare vs common letter pairs in these words.",
        "These words share an extreme in how “weird” or “normal” their letter combos are.",
    ],
    "consonant_runs": [
        "The pattern is about groups of consonants.",
        "Count how many blocks of consonants (without vowels) appear in each word.",
        "These words have an unusual number of consonant clusters.",
    ],
}

# Direction wording so hint 3 can say "highest" or "lowest" when it's an extreme-outlier rule
DIRECTION_HIGH = "high"  # "unusually high"
DIRECTION_LOW = "low"    # "unusually low"


def _direction_from_rule(rule: str) -> str:
    r = rule.lower()
    if "lowest" in r or "low " in r:
        return DIRECTION_LOW
    return DIRECTION_HIGH


def generate_hints(pattern: CandidatePattern) -> list[str]:
    """Return 3 hints that match the actual rule, from vague to specific."""
    metric = pattern.metric_a or "entropy"
    metric_hints = METRIC_HINTS.get(metric, METRIC_HINTS["entropy"])
    direction = _direction_from_rule(pattern.rule_description)

    # Build 3 hints that clearly point to the same idea
    h1 = metric_hints[0]
    h2 = metric_hints[1]
    # Third hint: add direction when it's extreme outliers
    if pattern.template_id == "extreme_outliers" and len(metric_hints) > 2:
        h3 = metric_hints[2]
        if "unusual" in h3 and ("high" not in h3.lower() and "low" not in h3.lower()):
            h3 = h3.replace("unusual", f"unusually {direction}", 1)
    else:
        h3 = metric_hints[2] if len(metric_hints) > 2 else metric_hints[1]
    return [h1, h2, h3][:3]
