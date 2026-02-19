"""
Countries daily puzzle: show countries that share a trait, player guesses the connection.
Uses the REST Countries API for accurate, dynamic country data.
"""
from __future__ import annotations

import json
import random
import time
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CountryCategory:
    key: str                          # unique identifier, e.g. "landlocked"
    label: str                        # human-readable answer, e.g. "Landlocked countries"
    accepted: list[str]               # accepted guess phrases
    difficulty: str                   # "easy", "medium", "hard"
    hints: list[str]                  # 3 progressive hints
    filter_fn: str                    # key into _FILTERS dispatch dict
    filter_args: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Filter functions: each takes a country dict and optional args, returns bool
# ---------------------------------------------------------------------------

_FILTERS: dict[str, Callable[[dict, dict], bool]] = {
    "region": lambda c, a: c.get("region") == a["value"],
    "subregion": lambda c, a: c.get("subregion") == a["value"],
    "landlocked": lambda c, _a: c.get("landlocked") is True,
    "island": lambda c, _a: len(c.get("borders", []) or []) == 0 and not c.get("landlocked", False),
    "population_above": lambda c, a: (c.get("population") or 0) >= a["threshold"],
    "population_below": lambda c, a: 0 < (c.get("population") or 0) <= a["threshold"],
    "area_above": lambda c, a: (c.get("area") or 0) >= a["threshold"],
    "area_below": lambda c, a: 0 < (c.get("area") or 0) <= a["threshold"],
    "starts_with": lambda c, a: (c.get("name") or {}).get("common", "").startswith(a["letter"]),
    "language": lambda c, a: a["value"] in (c.get("languages") or {}).values(),
    "currency": lambda c, a: a["value"] in [v.get("name") for v in (c.get("currencies") or {}).values()],
    "borders_count_above": lambda c, a: len(c.get("borders", []) or []) >= a["threshold"],
}


# ---------------------------------------------------------------------------
# Category definitions (~25 categories)
# ---------------------------------------------------------------------------

CATEGORIES: list[CountryCategory] = [
    # --- By continent (easy) ---
    CountryCategory("africa", "Countries in Africa", ["african countries", "countries in africa", "africa"], "easy", [
        "These are all countries.",
        "They're all on the same continent.",
        "Countries in Africa",
    ], "region", {"value": "Africa"}),
    CountryCategory("europe", "Countries in Europe", ["european countries", "countries in europe", "europe"], "easy", [
        "These are all countries.",
        "They share a continent.",
        "Countries in Europe",
    ], "region", {"value": "Europe"}),
    CountryCategory("asia", "Countries in Asia", ["asian countries", "countries in asia", "asia"], "easy", [
        "These are all countries.",
        "They share a continent.",
        "Countries in Asia",
    ], "region", {"value": "Asia"}),
    CountryCategory("americas", "Countries in the Americas", ["american countries", "countries in the americas", "americas", "western hemisphere"], "easy", [
        "These are all countries.",
        "They're in the Western Hemisphere.",
        "Countries in the Americas",
    ], "region", {"value": "Americas"}),
    CountryCategory("oceania", "Countries in Oceania", ["oceanian countries", "countries in oceania", "oceania", "pacific countries"], "easy", [
        "These are all countries.",
        "Think Pacific islands and Australia.",
        "Countries in Oceania",
    ], "region", {"value": "Oceania"}),

    # --- By subregion (medium) ---
    CountryCategory("south_america", "Countries in South America", ["south american countries", "south america"], "medium", [
        "These are all countries.",
        "They're all on the same subcontinent.",
        "Countries in South America",
    ], "subregion", {"value": "South America"}),
    CountryCategory("caribbean", "Caribbean countries", ["caribbean countries", "caribbean", "caribbean islands"], "medium", [
        "These are all countries.",
        "Think tropical islands and warm seas.",
        "Caribbean countries",
    ], "subregion", {"value": "Caribbean"}),
    CountryCategory("southeast_asia", "Countries in Southeast Asia", ["southeast asian countries", "southeast asia"], "medium", [
        "These are all countries.",
        "They're in a tropical part of one continent.",
        "Countries in Southeast Asia",
    ], "subregion", {"value": "South-Eastern Asia"}),
    CountryCategory("western_europe", "Countries in Western Europe", ["western european countries", "western europe"], "medium", [
        "These are all countries.",
        "They're on the western side of one continent.",
        "Countries in Western Europe",
    ], "subregion", {"value": "Western Europe"}),
    CountryCategory("northern_africa", "Countries in Northern Africa", ["north african countries", "northern africa", "north africa"], "medium", [
        "These are all countries.",
        "They border the Mediterranean or the Sahara.",
        "Countries in Northern Africa",
    ], "subregion", {"value": "Northern Africa"}),
    CountryCategory("middle_east", "Countries in the Middle East", ["middle eastern countries", "middle east"], "medium", [
        "These are all countries.",
        "They're in a region known for oil and ancient civilizations.",
        "Countries in the Middle East (Western Asia)",
    ], "subregion", {"value": "Western Asia"}),
    CountryCategory("central_america", "Countries in Central America", ["central american countries", "central america"], "medium", [
        "These are all countries.",
        "They connect two larger landmasses.",
        "Countries in Central America",
    ], "subregion", {"value": "Central America"}),

    # --- Geographic properties (medium/hard) ---
    CountryCategory("landlocked", "Landlocked countries", ["landlocked", "landlocked countries", "no coastline", "countries with no coast"], "medium", [
        "These countries share a geographic trait.",
        "None of them touch the ocean.",
        "Landlocked countries",
    ], "landlocked"),
    CountryCategory("island_nations", "Island nations", ["island nations", "island countries", "islands"], "medium", [
        "These countries share a geographic trait.",
        "They're completely surrounded by water.",
        "Island nations",
    ], "island"),

    # --- Population (medium/hard) ---
    CountryCategory("pop_above_100m", "Countries with over 100 million people", ["most populated", "populous countries", "over 100 million", "large population", "100 million"], "medium", [
        "These countries have something demographic in common.",
        "Think about their size in terms of people.",
        "Countries with population over 100 million",
    ], "population_above", {"threshold": 100_000_000}),
    CountryCategory("pop_below_1m", "Countries with under 1 million people", ["small countries", "tiny countries", "low population", "small population", "under 1 million"], "hard", [
        "These countries have something demographic in common.",
        "They're all very small in one specific way.",
        "Countries with population under 1 million",
    ], "population_below", {"threshold": 1_000_000}),

    # --- Area (medium/hard) ---
    CountryCategory("area_above_1m", "Countries larger than 1 million km\u00b2", ["biggest countries", "largest countries", "huge countries", "biggest by area", "1 million square"], "medium", [
        "These countries share a size trait.",
        "Look at a map \u2014 they take up a lot of space.",
        "Countries larger than 1 million square kilometers",
    ], "area_above", {"threshold": 1_000_000}),
    CountryCategory("area_below_1000", "Countries smaller than 1,000 km\u00b2", ["smallest countries", "tiny countries", "microstates", "small by area"], "hard", [
        "These countries share a size trait.",
        "You might barely see them on a map.",
        "Countries smaller than 1,000 square kilometers",
    ], "area_below", {"threshold": 1000}),

    # --- Letter-based (hard) ---
    CountryCategory("starts_with_m", "Countries starting with M", ["start with m", "letter m", "begins with m", "countries starting with m"], "hard", [
        "These country names share a spelling trait.",
        "Look at the first letter of each name.",
        "Countries whose names start with M",
    ], "starts_with", {"letter": "M"}),
    CountryCategory("starts_with_s", "Countries starting with S", ["start with s", "letter s", "begins with s", "countries starting with s"], "hard", [
        "These country names share a spelling trait.",
        "Look at the first letter of each name.",
        "Countries whose names start with S",
    ], "starts_with", {"letter": "S"}),
    CountryCategory("starts_with_c", "Countries starting with C", ["start with c", "letter c", "begins with c", "countries starting with c"], "hard", [
        "These country names share a spelling trait.",
        "Look at the first letter of each name.",
        "Countries whose names start with C",
    ], "starts_with", {"letter": "C"}),

    # --- Language-based (medium) ---
    CountryCategory("french_speaking", "French-speaking countries", ["french speaking", "francophone", "french language"], "medium", [
        "These countries share a linguistic trait.",
        "Bonjour!",
        "French-speaking countries",
    ], "language", {"value": "French"}),
    CountryCategory("spanish_speaking", "Spanish-speaking countries", ["spanish speaking", "hispanophone", "spanish language"], "medium", [
        "These countries share a linguistic trait.",
        "\u00a1Hola!",
        "Spanish-speaking countries",
    ], "language", {"value": "Spanish"}),
    CountryCategory("arabic_speaking", "Arabic-speaking countries", ["arabic speaking", "arabic language", "arab countries"], "medium", [
        "These countries share a linguistic trait.",
        "\u0645\u0631\u062d\u0628\u0627! (Marhaba!)",
        "Arabic-speaking countries",
    ], "language", {"value": "Arabic"}),

    # --- Connectivity (hard) ---
    CountryCategory("many_borders", "Countries bordering 6+ other countries", ["many borders", "most neighbors", "many neighbors", "countries with many borders"], "hard", [
        "These countries have a geographic connectivity trait.",
        "They have a lot of neighbors.",
        "Countries that border 6 or more other countries",
    ], "borders_count_above", {"threshold": 6}),
]


# ---------------------------------------------------------------------------
# REST Countries API — fetch & cache
# ---------------------------------------------------------------------------

_REST_API = "https://restcountries.com/v3.1/all"
# REST Countries `/all` endpoint accepts a limited number of `fields`.
# Keep this at <= 10 to avoid 400 responses.
_REST_FIELDS = "name,region,subregion,population,area,landlocked,languages,currencies,borders,flag"
_COUNTRY_CACHE: tuple[list[dict], float] | None = None
_COUNTRY_CACHE_TTL = 3600  # 1 hour


def _fetch_all_countries() -> list[dict]:
    """Fetch all countries from REST Countries API. Cached for 1 hour."""
    global _COUNTRY_CACHE
    now = time.time()
    if _COUNTRY_CACHE and (now - _COUNTRY_CACHE[1]) < _COUNTRY_CACHE_TTL:
        return _COUNTRY_CACHE[0]

    try:
        url = f"{_REST_API}?fields={_REST_FIELDS}"
        req = urllib.request.Request(url, headers={"User-Agent": "Patternfall/1.0 (countries game)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        if _COUNTRY_CACHE:
            return _COUNTRY_CACHE[0]
        return []

    if isinstance(data, list):
        _COUNTRY_CACHE = (data, now)
        return data
    return []


# ---------------------------------------------------------------------------
# Puzzle generation
# ---------------------------------------------------------------------------

DEFAULT_NUM_ITEMS = 6
MIN_ITEMS = 4


def _get_matching_countries(cat: CountryCategory) -> list[dict]:
    """Get country dicts matching this category's filter."""
    all_countries = _fetch_all_countries()
    filter_func = _FILTERS.get(cat.filter_fn)
    if not filter_func:
        return []

    matches = []
    for c in all_countries:
        try:
            if filter_func(c, cat.filter_args or {}):
                name = (c.get("name") or {}).get("common", "")
                if name:
                    matches.append(c)
        except Exception:
            continue
    return matches


def _pick_puzzle(rng: random.Random) -> dict | None:
    """Pick a category, fetch matching countries, select items."""
    cats = list(CATEGORIES)
    rng.shuffle(cats)

    for cat in cats:
        matches = _get_matching_countries(cat)
        if len(matches) < MIN_ITEMS:
            continue
        n = min(DEFAULT_NUM_ITEMS, len(matches))
        selected = rng.sample(matches, n)
        words = []
        flags = {}
        for c in selected:
            name = (c.get("name") or {}).get("common", "")
            words.append(name)
            flag = c.get("flag", "")
            if flag:
                flags[name] = flag
        return {
            "words": words,
            "flags": flags,
            "rule": cat.label,
            "hints": cat.hints,
            "difficulty": cat.difficulty,
            "category_key": cat.key,
        }
    return None


def get_today_puzzle() -> dict | None:
    """Deterministic puzzle for today based on date seed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(today)
    return _pick_puzzle(rng)


def get_random_puzzle() -> dict | None:
    """Random puzzle (different category each time)."""
    return _pick_puzzle(random.Random())


# ---------------------------------------------------------------------------
# Guess validation
# ---------------------------------------------------------------------------

def check_countries_guess(guess: str, rule: str, category_key: str = "") -> tuple[bool, str]:
    """Check user guess against the countries rule. Keyword/phrase matching."""
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."

    normalized = " ".join(g.split())
    rule_lower = rule.lower()

    # Check exact rule match
    if rule_lower in normalized or normalized in rule_lower:
        return True, "Correct!"

    # Check accepted phrases
    cat = None
    for c in CATEGORIES:
        if c.key == category_key or c.label == rule:
            cat = c
            break

    if cat:
        for phrase in cat.accepted:
            pl = phrase.lower()
            if pl in normalized or normalized in pl:
                return True, "Correct!"

    return False, "Not quite. Think about what these countries have in common."
