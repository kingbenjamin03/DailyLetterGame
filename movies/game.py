"""
Movies & TV daily puzzle: show movie/TV titles that share a connection,
player guesses the actor, director, or franchise.

Data is curated and hardcoded (no external API).
Mirrors the structure of trivia/countries modules.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class MovieCategory:
    key: str  # unique identifier
    label: str  # human-readable answer shown on reveal
    accepted: list[str]  # accepted guess phrases
    difficulty: str  # "easy", "medium", "hard"
    hints: list[str]  # 3 progressive hints
    puzzle_type: str  # "actor" | "director" | "franchise"
    items: list[str]  # clue titles


DEFAULT_NUM_ITEMS = 6
MIN_ITEMS = 4


def _accept(*phrases: str) -> list[str]:
    # Normalize and dedupe while preserving order.
    out: list[str] = []
    for p in phrases:
        s = " ".join((p or "").strip().lower().split())
        if s and s not in out:
            out.append(s)
    return out


def _hints_for(puzzle_type: str) -> list[str]:
    if puzzle_type == "actor":
        return [
            "These titles share a person in common.",
            "That person is an actor in all of them.",
            "Guess the actor.",
        ]
    if puzzle_type == "director":
        return [
            "These titles share a person in common.",
            "That person directed all of them.",
            "Guess the director.",
        ]
    # franchise
    return [
        "These titles are connected.",
        "They’re part of the same larger series.",
        "Guess the franchise.",
    ]


# Curated categories. Each has >= MIN_ITEMS clues.
# Notes:
# - For fairness, the accepted list includes the canonical answer and common variants.
# - Last-name-only guesses are accepted for a few very distinctive names.
CATEGORIES: list[MovieCategory] = [
    # --- Actors (easy/medium) ---
    MovieCategory(
        "actor_tom_hanks",
        "Tom Hanks",
        _accept("tom hanks", "hanks"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["Forrest Gump", "Cast Away", "Saving Private Ryan", "Big", "Toy Story", "Apollo 13"],
    ),
    MovieCategory(
        "actor_meryl_streep",
        "Meryl Streep",
        _accept("meryl streep", "streep"),
        "medium",
        _hints_for("actor"),
        "actor",
        ["The Devil Wears Prada", "Mamma Mia!", "Kramer vs. Kramer", "Sophie's Choice", "The Iron Lady", "Julie & Julia"],
    ),
    MovieCategory(
        "actor_leonardo_dicaprio",
        "Leonardo DiCaprio",
        _accept("leonardo dicaprio", "leo dicaprio", "dicaprio", "di caprio"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["Titanic", "Inception", "The Revenant", "The Wolf of Wall Street", "Shutter Island", "Catch Me If You Can"],
    ),
    MovieCategory(
        "actor_denzel_washington",
        "Denzel Washington",
        _accept("denzel washington", "washington", "denzel"),
        "medium",
        _hints_for("actor"),
        "actor",
        ["Training Day", "Remember the Titans", "The Equalizer", "Man on Fire", "Fences", "Inside Man"],
    ),
    MovieCategory(
        "actor_scarlett_johansson",
        "Scarlett Johansson",
        _accept("scarlett johansson", "scarlett johanssen", "johansson"),
        "medium",
        _hints_for("actor"),
        "actor",
        ["Lost in Translation", "Her", "Lucy", "Marriage Story", "Jojo Rabbit", "Black Widow"],
    ),
    MovieCategory(
        "actor_brad_pitt",
        "Brad Pitt",
        _accept("brad pitt", "pitt"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["Fight Club", "Se7en", "Once Upon a Time in Hollywood", "Ocean's Eleven", "Troy", "Moneyball"],
    ),
    MovieCategory(
        "actor_jennifer_lawrence",
        "Jennifer Lawrence",
        _accept("jennifer lawrence", "j law", "lawrence"),
        "medium",
        _hints_for("actor"),
        "actor",
        ["The Hunger Games", "Silver Linings Playbook", "American Hustle", "Passengers", "Winter's Bone", "X-Men: First Class"],
    ),
    MovieCategory(
        "actor_robert_downey_jr",
        "Robert Downey Jr.",
        _accept("robert downey jr", "robert downey jr.", "downey jr", "downey", "rdj"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["Iron Man", "Sherlock Holmes", "Avengers: Endgame", "Tropic Thunder", "Chaplin", "Zodiac"],
    ),
    MovieCategory(
        "actor_viola_davis",
        "Viola Davis",
        _accept("viola davis", "davis"),
        "hard",
        _hints_for("actor"),
        "actor",
        ["Fences", "The Help", "Ma Rainey's Black Bottom", "Widows", "Doubt", "Suicide Squad"],
    ),
    MovieCategory(
        "actor_keanu_reeves",
        "Keanu Reeves",
        _accept("keanu reeves", "keanu", "reeves"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["The Matrix", "John Wick", "Speed", "Point Break", "Constantine", "Bill & Ted's Excellent Adventure"],
    ),
    MovieCategory(
        "actor_natalie_portman",
        "Natalie Portman",
        _accept("natalie portman", "portman"),
        "medium",
        _hints_for("actor"),
        "actor",
        ["Black Swan", "V for Vendetta", "Léon: The Professional", "Thor", "Jackie", "Closer"],
    ),
    MovieCategory(
        "actor_will_smith",
        "Will Smith",
        _accept("will smith", "smith"),
        "easy",
        _hints_for("actor"),
        "actor",
        ["Men in Black", "Independence Day", "I Am Legend", "The Pursuit of Happyness", "Hitch", "Ali"],
    ),

    # --- Directors (medium/hard) ---
    MovieCategory(
        "director_christopher_nolan",
        "Christopher Nolan",
        _accept("christopher nolan", "nolan"),
        "easy",
        _hints_for("director"),
        "director",
        ["Inception", "Interstellar", "The Dark Knight", "Memento", "Dunkirk", "Oppenheimer"],
    ),
    MovieCategory(
        "director_steven_spielberg",
        "Steven Spielberg",
        _accept("steven spielberg", "spielberg"),
        "easy",
        _hints_for("director"),
        "director",
        ["Jaws", "E.T. the Extra-Terrestrial", "Jurassic Park", "Schindler's List", "Saving Private Ryan", "Raiders of the Lost Ark"],
    ),
    MovieCategory(
        "director_quentin_tarantino",
        "Quentin Tarantino",
        _accept("quentin tarantino", "tarantino"),
        "easy",
        _hints_for("director"),
        "director",
        ["Pulp Fiction", "Kill Bill: Vol. 1", "Django Unchained", "Inglourious Basterds", "Reservoir Dogs", "Once Upon a Time in Hollywood"],
    ),
    MovieCategory(
        "director_martin_scorsese",
        "Martin Scorsese",
        _accept("martin scorsese", "scorsese"),
        "medium",
        _hints_for("director"),
        "director",
        ["Goodfellas", "Taxi Driver", "The Departed", "Raging Bull", "The Wolf of Wall Street", "Shutter Island"],
    ),
    MovieCategory(
        "director_greta_gerwig",
        "Greta Gerwig",
        _accept("greta gerwig", "gerwig"),
        "hard",
        _hints_for("director"),
        "director",
        ["Lady Bird", "Little Women", "Barbie", "Nights and Weekends"],
    ),
    MovieCategory(
        "director_peter_jackson",
        "Peter Jackson",
        _accept("peter jackson", "jackson"),
        "medium",
        _hints_for("director"),
        "director",
        ["The Lord of the Rings: The Fellowship of the Ring", "The Lord of the Rings: The Two Towers", "The Lord of the Rings: The Return of the King", "King Kong", "The Hobbit: An Unexpected Journey", "The Lovely Bones"],
    ),
    MovieCategory(
        "director_kathryn_bigelow",
        "Kathryn Bigelow",
        _accept("kathryn bigelow", "bigelow"),
        "hard",
        _hints_for("director"),
        "director",
        ["The Hurt Locker", "Zero Dark Thirty", "Point Break", "Detroit", "Strange Days"],
    ),
    MovieCategory(
        "director_hayao_miyazaki",
        "Hayao Miyazaki",
        _accept("hayao miyazaki", "miyazaki"),
        "medium",
        _hints_for("director"),
        "director",
        ["Spirited Away", "My Neighbor Totoro", "Princess Mononoke", "Howl's Moving Castle", "Kiki's Delivery Service", "Ponyo"],
    ),

    # --- Franchises / universes (easy/medium) ---
    MovieCategory(
        "franchise_star_wars",
        "Star Wars",
        _accept("star wars", "starwars"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["A New Hope", "The Empire Strikes Back", "Return of the Jedi", "The Force Awakens", "The Last Jedi", "The Rise of Skywalker"],
    ),
    MovieCategory(
        "franchise_harry_potter",
        "Harry Potter",
        _accept("harry potter", "potter", "wizarding world", "the wizarding world"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["Sorcerer's Stone", "Chamber of Secrets", "Prisoner of Azkaban", "Goblet of Fire", "Order of the Phoenix", "Deathly Hallows"],
    ),
    MovieCategory(
        "franchise_marvel_mcu",
        "Marvel Cinematic Universe",
        _accept("marvel cinematic universe", "mcu", "marvel", "the mcu"),
        "medium",
        _hints_for("franchise"),
        "franchise",
        ["Iron Man", "The Avengers", "Captain America: Civil War", "Black Panther", "Avengers: Infinity War", "Avengers: Endgame"],
    ),
    MovieCategory(
        "franchise_james_bond",
        "James Bond",
        _accept("james bond", "bond", "007"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["Dr. No", "Goldfinger", "Thunderball", "Casino Royale", "Skyfall", "No Time to Die"],
    ),
    MovieCategory(
        "franchise_fast_and_furious",
        "Fast & Furious",
        _accept("fast and furious", "fast & furious", "fast furious", "the fast and the furious"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["The Fast and the Furious", "2 Fast 2 Furious", "Tokyo Drift", "Fast Five", "Furious 7", "F9"],
    ),
    MovieCategory(
        "franchise_lord_of_the_rings",
        "The Lord of the Rings",
        _accept("lord of the rings", "the lord of the rings", "lotr"),
        "medium",
        _hints_for("franchise"),
        "franchise",
        ["The Fellowship of the Ring", "The Two Towers", "The Return of the King", "The Hobbit: An Unexpected Journey", "The Hobbit: The Desolation of Smaug", "The Hobbit: The Battle of the Five Armies"],
    ),
    MovieCategory(
        "franchise_mission_impossible",
        "Mission: Impossible",
        _accept("mission impossible", "mission: impossible", "mi", "m:i"),
        "medium",
        _hints_for("franchise"),
        "franchise",
        ["Mission: Impossible", "Mission: Impossible 2", "Mission: Impossible III", "Ghost Protocol", "Rogue Nation", "Fallout"],
    ),
    MovieCategory(
        "franchise_jurassic_park",
        "Jurassic Park",
        _accept("jurassic park", "jurassic world"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["Jurassic Park", "The Lost World: Jurassic Park", "Jurassic Park III", "Jurassic World", "Fallen Kingdom", "Dominion"],
    ),
    MovieCategory(
        "franchise_matrix",
        "The Matrix",
        _accept("the matrix", "matrix"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["The Matrix", "The Matrix Reloaded", "The Matrix Revolutions", "The Matrix Resurrections"],
    ),
    MovieCategory(
        "franchise_pixar_toy_story",
        "Toy Story",
        _accept("toy story", "pixar toy story"),
        "easy",
        _hints_for("franchise"),
        "franchise",
        ["Toy Story", "Toy Story 2", "Toy Story 3", "Toy Story 4"],
    ),
]


def get_today_puzzle() -> dict | None:
    """Deterministic puzzle for today based on date seed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(today)
    return _pick_puzzle(rng)


def get_random_puzzle() -> dict | None:
    """Random puzzle."""
    return _pick_puzzle(random.Random())


def _pick_puzzle(rng: random.Random) -> dict | None:
    """Pick a category and sample clue items."""
    cats = list(CATEGORIES)
    rng.shuffle(cats)
    for cat in cats:
        if len(cat.items) < MIN_ITEMS:
            continue
        n = min(DEFAULT_NUM_ITEMS, len(cat.items))
        words = rng.sample(cat.items, n)
        return {
            "words": words,
            "rule": cat.label,
            "hints": cat.hints,
            "difficulty": cat.difficulty,
            "category_key": cat.key,
        }
    return None


def check_movies_guess(guess: str, rule: str, category_key: str = "") -> tuple[bool, str]:
    """Check user guess against the movies rule. Keyword/phrase matching."""
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."

    normalized = " ".join(g.split())
    rule_lower = (rule or "").strip().lower()

    if rule_lower and (rule_lower in normalized or normalized in rule_lower):
        return True, "Correct!"

    cat = None
    for c in CATEGORIES:
        if c.key == category_key or c.label == rule:
            cat = c
            break

    if cat:
        for phrase in cat.accepted:
            if phrase in normalized or normalized in phrase:
                return True, "Correct!"

    return False, "Not quite. Think about what these titles have in common."

