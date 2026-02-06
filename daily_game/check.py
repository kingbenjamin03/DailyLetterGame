"""
Check a user's guess against today's rule without revealing the answer.
Uses keyword/phrase matching first; optionally uses OpenAI to accept semantically similar wording.
"""
from __future__ import annotations

import os
import re

# For each metric, phrases that count as a correct guess (user can phrase it their way)
CORRECT_PHRASES: dict[str, list[str]] = {
    "length": ["length", "long", "short", "number of letters", "how long", "word length", "letter count"],
    "unique_letters": ["unique letters", "different letters", "distinct letters", "letter variety", "how many letters", "repeated letters", "unique characters"],
    "entropy": ["entropy", "letter repetition", "repetition", "predictable", "random letters", "letter distribution", "repeated letters"],
    "max_letter_frequency": ["one letter repeats", "repeated letter", "same letter", "letter repeats", "most repeated", "max letter", "one letter appears"],
    "vowel_ratio": ["vowel", "vowels", "consonants", "vowel ratio", "vowel proportion", "vowels and consonants"],
    "corpus_frequency": ["common", "rare", "frequency", "how often", "frequently", "corpus", "usage", "common words"],
    "vowel_spacing_std": ["vowel spacing", "vowels spaced", "spacing between vowels", "gaps between vowels", "vowel gaps", "where vowels", "vowels are spread", "uneven vowel", "even vowel", "distance between vowels"],
    "alphabetic_order_score": ["alphabetical", "alphabet order", "letters in order", "a to z", "abc order", "alphabetical order"],
    "bigram_probability": ["letter pairs", "two-letter", "bigram", "letter combinations", "pairs of letters", "two letter"],
    "edit_density": ["unusual letters", "rare letters", "letter combinations", "weird letters", "uncommon letters", "unusual combinations"],
    "consonant_runs": ["consonant", "consonants", "consonant cluster", "consonant run", "blocks of consonants", "consonant group"],
}


def normalize(guess: str) -> str:
    """Lowercase, collapse spaces, remove punctuation."""
    if not guess or not isinstance(guess, str):
        return ""
    s = guess.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


# Direction words: rule must and guess must agree on high vs low when rule has a direction
HIGH_DIRECTION = {"high", "highest", "most", "max", "maximum", "more", "greater", "greatest", "top", "most", "very high", "unusually high"}
LOW_DIRECTION = {"low", "lowest", "least", "min", "minimum", "fewer", "less", "fewest", "bottom", "very low", "unusually low"}


def _rule_direction(rule: str) -> str | None:
    """Return 'high', 'low', or None if the rule doesn't specify a clear direction."""
    r = rule.lower()
    if any(x in r for x in ("highest", "very high", "unusually high", "high ")):
        return "high"
    if any(x in r for x in ("lowest", "very low", "unusually low", " low ")):
        return "low"
    return None


def _guess_expresses_direction(guess_normalized: str, direction: str) -> bool:
    """True if the guess clearly expresses the same direction (high or low)."""
    if direction == "high":
        return any(w in guess_normalized for w in HIGH_DIRECTION)
    if direction == "low":
        return any(w in guess_normalized for w in LOW_DIRECTION)
    return True


def _keyword_match(guess: str, rule: str, metric_a: str | None) -> bool:
    """True if guess matches by keywords/phrases and (when relevant) same direction."""
    g = normalize(guess)
    if not g or len(g) < 3:
        return False
    rule_normalized = normalize(rule.replace("_", " "))
    rule_direction = _rule_direction(rule)

    # If the rule has a direction, guess must express that same direction or we reject
    if rule_direction is not None and not _guess_expresses_direction(g, rule_direction):
        return False

    # Exact substring: full rule in guess or full guess in rule (strong signal)
    if g in rule_normalized or rule_normalized in g:
        return True
    metric = (metric_a or "").strip()
    for phrase in CORRECT_PHRASES.get(metric, []):
        if phrase in g or phrase.replace(" ", "") in g.replace(" ", ""):
            return True
    # Require at least 3 matching tokens from the rule (not just 2) to avoid loose matches
    key_part = rule.replace("Words with highest ", "").replace("Words with lowest ", "").replace("_", " ")
    tokens = [t for t in key_part.lower().split() if len(t) > 2 and t not in ("the", "and", "for", "have", "are", "all", "words", "with", "very", "unusually")]
    if tokens and sum(1 for t in tokens if t in g) >= 3:
        return True
    return False


def _ai_semantic_match(guess: str, rule: str) -> tuple[bool, str | None]:
    """
    Use OpenAI to decide if the guess describes the same pattern as the rule.
    Returns (matched, error_message). If error_message is set, the API failed.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return False, None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = (
            "You are judging a word puzzle. The official rule is:\n"
            f'"{rule}"\n\n'
            "The user's guess is:\n"
            f'"{guess}"\n\n'
            "Does the user's guess correctly describe the SAME pattern, even in different words? "
            "Answer with exactly one word: YES or NO."
        )
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",  # cheapest option for short yes/no
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
        )
        text = (resp.choices[0].message.content or "").strip().upper()
        if "YES" in text:
            return True, None
        return False, None
    except Exception as e:
        return False, str(e)


def check_guess(guess: str, rule: str, metric_a: str | None) -> tuple[bool, str]:
    """
    Return (correct, message). When OPENAI_API_KEY is set, the AI is the arbiter of
    meaning (so we don't accept keyword-only matches that are wrong). Otherwise
    we rely on stricter keyword matching (direction + more tokens).
    """
    g = normalize(guess)
    if not g or len(g) < 3:
        return False, "Type a short description of what the words have in common."

    keyword_ok = _keyword_match(guess, rule, metric_a)
    # When AI is available, use it as the source of truth so we go by meaning, not just keywords
    if os.environ.get("OPENAI_API_KEY"):
        matched, ai_error = _ai_semantic_match(guess, rule)
        if ai_error:
            # Fall back to keyword only if API failed
            return (True, "Correct!") if keyword_ok else (False, "Not quite — try the hints or rephrase. (AI check unavailable.)")
        return (True, "Correct!") if matched else (False, "Not quite — try the hints or describe the pattern in different words.")

    if keyword_ok:
        return True, "Correct!"
    return False, "Not quite — try the hints or describe the pattern in different words."
