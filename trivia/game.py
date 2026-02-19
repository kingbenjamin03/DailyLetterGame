"""
Trivia daily puzzle: show items from a Wikipedia category, player guesses the category.
Uses the Wikipedia API to fetch category members dynamically.
"""
from __future__ import annotations

import json
import random
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TriviaCategory:
    wiki_category: str  # e.g. "Category:Chemical_elements"
    label: str  # human-readable rule, e.g. "Chemical elements"
    accepted: list[str]  # accepted guess phrases
    difficulty: str  # "easy", "medium", "hard"
    hints: list[str]  # 3 progressive hints
    exclude: list[str] | None = None  # titles to exclude (lowercase substrings)


CATEGORIES: list[TriviaCategory] = [
    # --- Science ---
    TriviaCategory("Category:Chemical_elements", "Chemical elements", ["elements", "chemical elements", "periodic table", "periodic table elements"], "easy", [
        "These are all scientific terms.",
        "They're all found on the periodic table.",
        "Chemical elements",
    ], exclude=["chemical element", "periodic table", "chemical symbol", "collecting", "predicted", "mineral", "roles of"]),
    TriviaCategory("Category:Planets_of_the_Solar_System", "Planets in our solar system", ["planets", "solar system", "planets in the solar system", "planets in our solar system"], "easy", [
        "Look up at the night sky.",
        "They all orbit the same star.",
        "Planets in our solar system",
    ], exclude=["nomenclature", "inferior and superior", "mnemonic", "beyond neptune", "classical planet", "planets of the", "definition of"]),
    TriviaCategory("Category:Constellations_listed_by_Ptolemy", "Constellations", ["constellations", "star constellations", "constellations in the sky"], "medium", [
        "These are all things you can see at night.",
        "They're patterns of stars.",
        "Constellations",
    ]),
    TriviaCategory("Category:Noble_gases", "Noble gases", ["noble gases", "inert gases", "group 18 elements"], "medium", [
        "These are all chemical substances.",
        "They're famously unreactive.",
        "Noble gases",
    ], exclude=["noble gas", "inert", "chemically", "mixture", "ramsay", "penning", "alternative", "liquid"]),

    # --- Geography ---
    TriviaCategory("Category:Countries_in_Africa", "Countries in Africa", ["african countries", "countries in africa", "africa"], "medium", [
        "These are all places.",
        "They're all on the same continent.",
        "Countries in Africa",
    ]),
    TriviaCategory("Category:Countries_in_South_America", "Countries in South America", ["south american countries", "countries in south america", "south america"], "medium", [
        "These are all places.",
        "They're all on the same continent.",
        "Countries in South America",
    ], exclude=["bolivarian"]),
    TriviaCategory("Category:Countries_in_Europe", "Countries in Europe", ["european countries", "countries in europe", "europe"], "medium", [
        "These are all places.",
        "They're all on the same continent.",
        "Countries in Europe",
    ]),
    TriviaCategory("Category:Countries_in_Asia", "Countries in Asia", ["asian countries", "countries in asia", "asia"], "medium", [
        "These are all places.",
        "They're all on the same continent.",
        "Countries in Asia",
    ]),
    TriviaCategory("Category:Capitals_in_Europe", "European capital cities", ["european capitals", "capital cities", "capitals in europe", "european capital cities"], "hard", [
        "These are all cities.",
        "Each one is the most important city in its country.",
        "European capital cities",
    ], exclude=["capital of culture", "green capital", "youth capital"]),
    TriviaCategory("Category:Deserts_of_Africa", "Deserts in Africa", ["african deserts", "deserts in africa", "deserts"], "hard", [
        "These are all geographic features.",
        "They're very dry places on one continent.",
        "Deserts in Africa",
    ]),
    TriviaCategory("Category:Islands_of_Greece", "Greek islands", ["greek islands", "islands of greece", "islands in greece"], "hard", [
        "These are all places surrounded by water.",
        "They're in the Mediterranean.",
        "Greek islands",
    ]),

    # --- Animals ---
    TriviaCategory("Category:Eagles", "Eagles", ["eagles", "eagle species", "types of eagles"], "medium", [
        "These are all birds.",
        "They're large birds of prey.",
        "Eagles",
    ], exclude=["eagle feather", "eagle law"]),
    # --- Food & Drink ---
    TriviaCategory("Category:English_cheeses", "English cheeses", ["english cheese", "cheeses", "cheese", "english cheeses", "british cheese"], "medium", [
        "These are all food items.",
        "They're all dairy products from one country.",
        "English cheeses",
    ]),
    TriviaCategory("Category:French_cheeses", "French cheeses", ["french cheese", "cheeses", "cheese", "french cheeses"], "medium", [
        "These are all food items.",
        "They're all dairy products from one country.",
        "French cheeses",
    ], exclude=["template", "french cheese"]),
    TriviaCategory("Category:Italian_cheeses", "Italian cheeses", ["italian cheese", "cheeses", "cheese", "italian cheeses"], "medium", [
        "These are all food items.",
        "They're all dairy products from one country.",
        "Italian cheeses",
    ]),
    TriviaCategory("Category:Spices", "Spices", ["spices", "cooking spices", "types of spices"], "medium", [
        "These are all found in the kitchen.",
        "They add flavor to food.",
        "Spices",
    ], exclude=["spice trade", "spice mix", "jerk"]),
    TriviaCategory("Category:Grape_varieties", "Grape varieties", ["grape varieties", "grapes", "types of grapes", "wine grapes"], "hard", [
        "These are all plants.",
        "They're used to make a popular beverage.",
        "Grape varieties",
    ], exclude=["vitisin"]),

    # --- Music & Arts ---
    TriviaCategory("Category:Musical_instruments", "Musical instruments", ["musical instruments", "instruments", "music instruments"], "easy", [
        "These all make sound.",
        "Musicians use them to perform.",
        "Musical instruments",
    ], exclude=["instrument", "recording studio", "folk ", "thomann", "acoustic resonance", "music technology"]),
    TriviaCategory("Category:Dances", "Dances", ["dances", "types of dance", "dance styles", "dance"], "medium", [
        "These are all physical activities.",
        "They involve rhythmic movement to music.",
        "Dances",
    ], exclude=["solo dance", "aerial dance", "the strictly", "dance competition"]),
    TriviaCategory("Category:Art_movements", "Art movements", ["art movements", "art styles", "artistic movements"], "hard", [
        "These are all cultural phenomena.",
        "They describe different styles of visual art across history.",
        "Art movements",
    ]),

    # --- Sports & Games ---
    TriviaCategory("Category:Summer_Olympic_sports", "Summer Olympic sports", ["olympic sports", "sports in the olympics", "summer olympic sports"], "medium", [
        "These are all physical activities.",
        "Athletes compete in them every four years.",
        "Olympic sports",
    ], exclude=["association of", "federation", "cheerleading", "sport of"]),
    TriviaCategory("Category:Martial_arts", "Martial arts", ["martial arts", "fighting styles", "combat sports"], "medium", [
        "These are all physical disciplines.",
        "They involve combat or self-defense techniques.",
        "Martial arts",
    ], exclude=["martial art", "hansoku", "tradition"]),
    TriviaCategory("Category:Board_games", "Board games", ["board games", "tabletop games"], "easy", [
        "These are all things you play.",
        "They're played on a flat surface with pieces.",
        "Board games",
    ], exclude=["association", "tiger game", "reversed", "board game"]),
    # --- History & Culture ---
    TriviaCategory("Category:Twelve_Olympians", "Greek Olympian gods", ["greek gods", "olympian gods", "twelve olympians", "gods of greece", "olympians"], "medium", [
        "These are all figures from mythology.",
        "They lived on Mount Olympus.",
        "Greek Olympian gods",
    ], exclude=["twelve olympians", "fontana"]),
    TriviaCategory("Category:Pharaohs_of_the_Eighteenth_Dynasty_of_Egypt", "Egyptian pharaohs", ["pharaohs", "egyptian pharaohs", "rulers of egypt"], "hard", [
        "These are all historical figures.",
        "They ruled an ancient civilization along the Nile.",
        "Egyptian pharaohs",
    ], exclude=["functions of", "pharaoh"]),
    TriviaCategory("Category:Seven_Wonders_of_the_Ancient_World", "Seven Wonders of the Ancient World", ["wonders of the world", "seven wonders", "ancient wonders", "wonders of the ancient world"], "medium", [
        "These are all famous ancient structures.",
        "There were originally seven of them.",
        "Seven Wonders of the Ancient World",
    ], exclude=["seven wonders", "eighth wonder", "video game", "board game", "7 wonders", "octo mundi", "walls of babylon", "wonders of the world"]),
    TriviaCategory("Category:Mythological_creatures", "Mythological creatures", ["mythological creatures", "mythical creatures", "legendary creatures", "myths"], "medium", [
        "These are all beings from stories.",
        "None of them actually exist (probably).",
        "Mythological creatures",
    ]),

    # --- Language & Literature ---
    TriviaCategory("Category:Western_astrological_signs", "Zodiac signs", ["zodiac signs", "zodiac", "astrological signs", "star signs", "horoscope signs"], "easy", [
        "There are twelve of these.",
        "They're associated with birthdates.",
        "Zodiac signs",
    ], exclude=["astrological symbol", "chart rulership", "domicile", "detriment", "triplicity"]),
    TriviaCategory("Category:Phobias", "Phobias", ["phobias", "fears", "types of phobias"], "hard", [
        "These are all psychological terms.",
        "They describe irrational fears.",
        "Phobias",
    ]),

    # --- Technology ---
    TriviaCategory("Category:Programming_languages", "Programming languages", ["programming languages", "coding languages", "computer languages"], "easy", [
        "These are all used by engineers.",
        "You use them to tell computers what to do.",
        "Programming languages",
    ]),
    TriviaCategory("Category:Cryptocurrencies", "Cryptocurrencies", ["cryptocurrencies", "crypto", "digital currencies", "cryptocurrency"], "medium", [
        "These are all digital assets.",
        "They use blockchain technology.",
        "Cryptocurrencies",
    ], exclude=["tokenized", "exchange", "financial", "the dao", "metamask", "blockchain", "mining", "wallet", "cryptocurrency", "virtual currency", "sovereign currency", "smart contract", "cryptonote"]),

    # --- Miscellaneous ---
    TriviaCategory("Category:Gemstones", "Gemstones", ["gemstones", "gems", "precious stones", "jewels"], "easy", [
        "These are all valuable natural objects.",
        "They're found underground and used in jewelry.",
        "Gemstones",
    ], exclude=["gemstone", "species", "metal-coated"]),
]

# Wikipedia API
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_WIKI_CACHE: dict[str, tuple[list[str], float]] = {}
_WIKI_CACHE_TTL = 3600  # 1 hour

# Prefixes to skip in category members
_SKIP_PREFIXES = ("List of", "Lists of", "Template:", "Category:", "Wikipedia:", "File:",
                   "Portal:", "Draft:", "Module:", "Index of", "Outline of", "History of",
                   "Timeline of", "Types of")

DEFAULT_NUM_ITEMS = 6
MIN_ITEMS = 4


def _fetch_category_members(wiki_category: str, limit: int = 100, exclude: list[str] | None = None) -> list[str]:
    """Fetch page titles from a Wikipedia category. Returns cleaned titles."""
    now = time.time()
    cached = _WIKI_CACHE.get(wiki_category)
    if cached and (now - cached[1]) < _WIKI_CACHE_TTL:
        return cached[0]

    try:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": wiki_category,
            "cmlimit": str(limit),
            "cmtype": "page",
            "format": "json",
        }
        qs = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params.items())
        url = f"{_WIKI_API}?{qs}"
        req = urllib.request.Request(url, headers={"User-Agent": "Patternfall/1.0 (trivia game)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return _WIKI_CACHE.get(wiki_category, ([], 0))[0]

    members = data.get("query", {}).get("categorymembers", [])
    titles: list[str] = []
    for m in members:
        title = (m.get("title") or "").strip()
        if not title:
            continue
        if any(title.startswith(p) for p in _SKIP_PREFIXES):
            continue
        # Clean up: remove disambiguation parentheticals
        if " (" in title:
            title = title[:title.index(" (")]
        # Skip very long titles (likely articles about concepts, not instances)
        if len(title) > 35:
            continue
        # Apply per-category excludes
        if exclude:
            title_lower = title.lower()
            if any(ex in title_lower for ex in exclude):
                continue
        titles.append(title)

    _WIKI_CACHE[wiki_category] = (titles, now)
    return titles


def _load_approved_suggestions() -> list[dict]:
    """Load approved user-submitted trivia puzzles (with pre-specified items)."""
    path = Path(__file__).resolve().parent.parent / "data" / "suggestions.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_sug = json.load(f)
        result = []
        for s in all_sug:
            if s.get("category") == "trivia" and s.get("status") == "approved":
                items = s.get("items", [])
                if len(items) < MIN_ITEMS:
                    continue
                result.append({
                    "label": s.get("label", ""),
                    "accepted": s.get("accepted", [s.get("label", "").lower()]),
                    "difficulty": s.get("difficulty", "medium"),
                    "hints": s.get("hints", ["These things have something in common.", "Think about what category links them.", "Guess the connection."]),
                    "items": items,
                    "id": s.get("id", "user"),
                })
        return result
    except Exception:
        return []


def get_today_puzzle() -> dict | None:
    """Deterministic puzzle for today based on date seed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(today)
    return _pick_puzzle(rng)


def get_random_puzzle() -> dict | None:
    """Random puzzle (different category each time)."""
    return _pick_puzzle(random.Random())


def _pick_puzzle(rng: random.Random) -> dict | None:
    """Pick a category, fetch members, select items. Also draws from user suggestions."""
    # Build a pool of (type, entry) — either TriviaCategory or a user suggestion dict
    pool: list[tuple[str, object]] = [("wiki", c) for c in CATEGORIES]
    for sug in _load_approved_suggestions():
        pool.append(("user", sug))
    rng.shuffle(pool)

    for kind, entry in pool:
        if kind == "wiki":
            cat = entry  # type: ignore[assignment]
            members = _fetch_category_members(cat.wiki_category, exclude=cat.exclude)
            if len(members) < MIN_ITEMS:
                continue
            n = min(DEFAULT_NUM_ITEMS, len(members))
            words = rng.sample(members, n)
            return {
                "words": words,
                "rule": cat.label,
                "hints": cat.hints,
                "difficulty": cat.difficulty,
                "category_key": cat.wiki_category,
            }
        else:
            sug = entry  # type: ignore[assignment]
            items = sug["items"]
            n = min(DEFAULT_NUM_ITEMS, len(items))
            words = rng.sample(items, n)
            return {
                "words": words,
                "rule": sug["label"],
                "hints": sug["hints"],
                "difficulty": sug["difficulty"],
                "category_key": sug["id"],
            }
    return None


def check_trivia_guess(guess: str, rule: str, category_key: str = "") -> tuple[bool, str]:
    """Check user guess against the trivia rule. Keyword/phrase matching."""
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."

    normalized = " ".join(g.split())
    rule_lower = rule.lower()

    # Check exact rule match
    if rule_lower in normalized or normalized in rule_lower:
        return True, "Correct!"

    # Check accepted phrases (built-in categories)
    cat = None
    for c in CATEGORIES:
        if c.wiki_category == category_key or c.label == rule:
            cat = c
            break

    if cat:
        for phrase in cat.accepted:
            pl = phrase.lower()
            if pl in normalized or normalized in pl:
                return True, "Correct!"

    # Check user suggestions by label/id
    if cat is None:
        for sug in _load_approved_suggestions():
            if sug["id"] == category_key or sug["label"] == rule:
                for phrase in sug["accepted"]:
                    pl = phrase.lower()
                    if pl in normalized or normalized in pl:
                        return True, "Correct!"
                break

    # Partial feedback
    return False, "Not quite. Think about what category all of these belong to."
