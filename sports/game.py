"""
Sports daily puzzle: pick a leaderboard (league + stat), show top player names,
user guesses what stat they all lead in. Uses hardcoded data (no DB required).
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Hardcoded all-time career leaderboard data
# Each entry: (league_id, stat_name) -> list of top player names (ranked)
# ---------------------------------------------------------------------------

LEADERBOARDS: dict[tuple[str, str], list[str]] = {
    # NFL
    ("nfl", "pass_td"): [
        "Tom Brady", "Drew Brees", "Peyton Manning", "Brett Favre",
        "Aaron Rodgers", "Dan Marino", "Philip Rivers", "Ben Roethlisberger",
        "Eli Manning", "Matt Ryan", "Russell Wilson", "Matthew Stafford",
    ],
    ("nfl", "pass_yds"): [
        "Tom Brady", "Drew Brees", "Peyton Manning", "Brett Favre",
        "Philip Rivers", "Dan Marino", "Ben Roethlisberger", "Eli Manning",
        "Matt Ryan", "Aaron Rodgers", "Matthew Stafford", "Russell Wilson",
    ],
    ("nfl", "rush_td"): [
        "Emmitt Smith", "LaDainian Tomlinson", "Marcus Allen", "Walter Payton",
        "Adrian Peterson", "Shaun Alexander", "Jim Brown", "Marshall Faulk",
        "Derrick Henry", "Barry Sanders", "Curtis Martin", "Franco Harris",
    ],
    ("nfl", "rush_yds"): [
        "Emmitt Smith", "Walter Payton", "Frank Gore", "Barry Sanders",
        "Adrian Peterson", "Curtis Martin", "LaDainian Tomlinson", "Jerome Bettis",
        "Eric Dickerson", "Tony Dorsett", "Jim Brown", "Marshall Faulk",
    ],
    ("nfl", "receptions"): [
        "Jerry Rice", "Larry Fitzgerald", "Tony Gonzalez", "Jason Witten",
        "Marvin Harrison", "Tim Brown", "Travis Kelce", "Andre Johnson",
        "Reggie Wayne", "Larry Centers", "Cris Carter", "Anquan Boldin",
    ],
    ("nfl", "rec_yds"): [
        "Jerry Rice", "Larry Fitzgerald", "Terrell Owens", "Randy Moss",
        "Isaac Bruce", "Tim Brown", "Marvin Harrison", "Reggie Wayne",
        "Andre Johnson", "Steve Smith", "Henry Ellard", "Torry Holt",
    ],
    ("nfl", "rec_td"): [
        "Jerry Rice", "Randy Moss", "Terrell Owens", "Cris Carter",
        "Marvin Harrison", "Larry Fitzgerald", "Antonio Gates", "Tim Brown",
        "Rob Gronkowski", "Travis Kelce", "Tony Gonzalez", "Steve Largent",
    ],
    # NBA
    ("nba", "pts"): [
        "LeBron James", "Kareem Abdul-Jabbar", "Karl Malone", "Kobe Bryant",
        "Michael Jordan", "Dirk Nowitzki", "Wilt Chamberlain", "Shaquille O'Neal",
        "Carmelo Anthony", "Moses Malone", "Elvin Hayes", "Kevin Durant",
    ],
    ("nba", "trb"): [
        "Wilt Chamberlain", "Bill Russell", "Kareem Abdul-Jabbar", "Elvin Hayes",
        "Moses Malone", "Tim Duncan", "Karl Malone", "Robert Parish",
        "Kevin Garnett", "Nate Thurmond", "Walt Bellamy", "Dwight Howard",
    ],
    ("nba", "ast"): [
        "John Stockton", "Jason Kidd", "Chris Paul", "Steve Nash",
        "Mark Jackson", "Magic Johnson", "Oscar Robertson", "LeBron James",
        "Isiah Thomas", "Gary Payton", "Russell Westbrook", "Andre Miller",
    ],
    ("nba", "stl"): [
        "John Stockton", "Jason Kidd", "Michael Jordan", "Gary Payton",
        "Chris Paul", "Maurice Cheeks", "Scottie Pippen", "Clyde Drexler",
        "Hakeem Olajuwon", "Alvin Robertson", "Karl Malone", "Allen Iverson",
    ],
    ("nba", "blk"): [
        "Hakeem Olajuwon", "Dikembe Mutombo", "Kareem Abdul-Jabbar", "Mark Eaton",
        "Tim Duncan", "David Robinson", "Patrick Ewing", "Shaquille O'Neal",
        "Tree Rollins", "Robert Parish", "Alonzo Mourning", "Marcus Camby",
    ],
    # NHL
    ("nhl", "goals"): [
        "Wayne Gretzky", "Gordie Howe", "Jaromir Jagr", "Brett Hull",
        "Marcel Dionne", "Phil Esposito", "Mike Gartner", "Mark Messier",
        "Steve Yzerman", "Mario Lemieux", "Alex Ovechkin", "Teemu Selanne",
    ],
    ("nhl", "assists"): [
        "Wayne Gretzky", "Ron Francis", "Mark Messier", "Ray Bourque",
        "Jaromir Jagr", "Paul Coffey", "Adam Oates", "Steve Yzerman",
        "Gordie Howe", "Marcel Dionne", "Mario Lemieux", "Joe Sakic",
    ],
    ("nhl", "points"): [
        "Wayne Gretzky", "Jaromir Jagr", "Mark Messier", "Gordie Howe",
        "Ron Francis", "Marcel Dionne", "Steve Yzerman", "Mario Lemieux",
        "Joe Sakic", "Phil Esposito", "Ray Bourque", "Joe Thornton",
    ],
}

# Human-readable rule and accepted guess phrases per (league_id, stat_name)
SPORT_RULES: dict[tuple[str, str], tuple[str, list[str]]] = {
    ("nfl", "pass_td"): ("NFL career passing touchdowns", ["passing touchdowns", "pass td", "career passing touchdowns", "nfl passing touchdowns", "most passing tds"]),
    ("nfl", "pass_yds"): ("NFL career passing yards", ["passing yards", "pass yds", "career passing yards", "nfl passing yards"]),
    ("nfl", "rush_td"): ("NFL career rushing touchdowns", ["rushing touchdowns", "rush td", "career rushing touchdowns", "nfl rushing touchdowns"]),
    ("nfl", "rush_yds"): ("NFL career rushing yards", ["rushing yards", "rush yds", "career rushing yards", "nfl rushing yards"]),
    ("nfl", "receptions"): ("NFL career receptions", ["receptions", "career receptions", "nfl receptions", "most receptions"]),
    ("nfl", "rec_yds"): ("NFL career receiving yards", ["receiving yards", "rec yds", "career receiving yards", "nfl receiving yards"]),
    ("nfl", "rec_td"): ("NFL career receiving touchdowns", ["receiving touchdowns", "rec td", "career receiving touchdowns", "nfl receiving touchdowns"]),
    ("nba", "pts"): ("NBA career points", ["points", "career points", "nba points", "scoring", "all-time points"]),
    ("nba", "trb"): ("NBA career total rebounds", ["rebounds", "total rebounds", "career rebounds", "nba rebounds"]),
    ("nba", "ast"): ("NBA career assists", ["assists", "career assists", "nba assists"]),
    ("nba", "stl"): ("NBA career steals", ["steals", "career steals", "nba steals"]),
    ("nba", "blk"): ("NBA career blocks", ["blocks", "career blocks", "nba blocks"]),
    ("nhl", "goals"): ("NHL career goals", ["goals", "career goals", "nhl goals", "most goals"]),
    ("nhl", "assists"): ("NHL career assists", ["assists", "career assists", "nhl assists"]),
    ("nhl", "points"): ("NHL career points", ["points", "career points", "nhl points"]),
}

DEFAULT_NUM_PLAYERS = 6


def _hints_for(league_id: str, stat_name: str) -> list[str]:
    """Three progressive hints for this leaderboard."""
    rule, _ = SPORT_RULES.get((league_id, stat_name), (f"{league_id.upper()} career {stat_name}", []))
    league_upper = league_id.upper()
    if league_id == "nfl":
        return [
            f"These are {league_upper} players.",
            "They're ranked by a single career stat.",
            rule,
        ]
    if league_id == "nba":
        return [
            f"These are {league_upper} players.",
            "Think all-time career leaderboards.",
            rule,
        ]
    if league_id == "nhl":
        return [
            f"These are {league_upper} players.",
            "They're among the all-time leaders in one stat.",
            rule,
        ]
    return [
        f"These are {league_upper} players.",
        "They're stat leaders.",
        rule,
    ]


def _build_puzzle(league_id: str, stat_name: str) -> dict | None:
    key = (league_id, stat_name)
    players = LEADERBOARDS.get(key)
    if not players or len(players) < DEFAULT_NUM_PLAYERS:
        return None
    rule, _ = SPORT_RULES.get(key, (f"{league_id.upper()} career {stat_name}", []))
    hints = _hints_for(league_id, stat_name)
    return {
        "words": players[:DEFAULT_NUM_PLAYERS],
        "rule": rule,
        "hints": hints,
        "difficulty": "medium",
        "league_id": league_id,
        "stat_name": stat_name,
    }


def _load_approved_suggestions() -> list[dict]:
    """Load approved user-submitted sports puzzles from data/suggestions.json."""
    path = Path(__file__).resolve().parent.parent / "data" / "suggestions.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            all_sug = json.load(f)
        result = []
        for s in all_sug:
            if s.get("category") == "sports" and s.get("status") == "approved":
                items = s.get("items", [])
                if len(items) < 4:
                    continue
                result.append({
                    "label": s.get("label", ""),
                    "accepted": s.get("accepted", [s.get("label", "").lower()]),
                    "difficulty": s.get("difficulty", "medium"),
                    "hints": s.get("hints", ["These athletes share a statistical achievement.", "Look at the numbers — what connects them?", "Guess the stat or leaderboard."]),
                    "items": items,
                    "id": s.get("id", "user"),
                })
        return result
    except Exception:
        return []


def get_today_puzzle() -> dict | None:
    """Deterministic puzzle for today: seed by date, pick one leaderboard."""
    suggestions = _load_approved_suggestions()
    built_in_keys = list(LEADERBOARDS.keys())
    pool_size = len(built_in_keys) + len(suggestions)
    if pool_size == 0:
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(today)
    idx = rng.randrange(pool_size)
    if idx < len(built_in_keys):
        league_id, stat_name = built_in_keys[idx]
        return _build_puzzle(league_id, stat_name)
    sug = suggestions[idx - len(built_in_keys)]
    players = sug["items"][:DEFAULT_NUM_PLAYERS]
    return {
        "words": players,
        "rule": sug["label"],
        "hints": sug["hints"],
        "difficulty": sug["difficulty"],
        "league_id": "",
        "stat_name": "",
        "_accepted": sug["accepted"],
    }


def get_random_puzzle() -> dict | None:
    """Random puzzle (different leaderboard each time)."""
    suggestions = _load_approved_suggestions()
    built_in_keys = list(LEADERBOARDS.keys())
    pool_size = len(built_in_keys) + len(suggestions)
    if pool_size == 0:
        return None
    idx = random.randrange(pool_size)
    if idx < len(built_in_keys):
        league_id, stat_name = built_in_keys[idx]
        return _build_puzzle(league_id, stat_name)
    sug = suggestions[idx - len(built_in_keys)]
    players = sug["items"][:DEFAULT_NUM_PLAYERS]
    return {
        "words": players,
        "rule": sug["label"],
        "hints": sug["hints"],
        "difficulty": sug["difficulty"],
        "league_id": "",
        "stat_name": "",
        "_accepted": sug["accepted"],
    }


# Wikipedia search URL for player info (no DB needed)
_WIKI_BASE = "https://en.wikipedia.org/wiki/"


def get_player_info(name: str, league_id: str = "") -> dict | None:
    """Return player info with a Wikipedia link. No DB required."""
    name = (name or "").strip()
    if not name:
        return None
    wiki_slug = name.replace(" ", "_")
    return {
        "name": name,
        "profile_url": f"{_WIKI_BASE}{wiki_slug}",
        "photo_url": None,
        "league_id": league_id,
    }


def check_sports_guess(
    guess: str, rule: str, league_id: str = "", stat_name: str = "", season_year: int | None = None,
    accepted_override: list[str] | None = None,
) -> tuple[bool, str]:
    """
    Check user guess against the puzzle rule. Uses keyword/phrase matching.
    Returns (correct, message).
    """
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."
    _, built_in_accepted = SPORT_RULES.get((league_id, stat_name), ("", []))
    accepted = list(accepted_override or []) + list(built_in_accepted)
    # Normalize: collapse spaces
    normalized = " ".join(g.split())
    for phrase in accepted:
        if phrase.lower() in normalized or normalized in phrase.lower():
            return True, "Correct!"
    # Also accept the exact rule
    rule_lower = rule.lower()
    if rule_lower in normalized or normalized in rule_lower:
        return True, "Correct!"
    # Partial: if they said the stat or league, give a nudge
    if league_id and league_id in normalized and stat_name and stat_name.replace("_", " ") in normalized:
        return False, "Right league and stat idea—try wording it like the answer (e.g. 'NFL career passing touchdowns')."
    return False, "Not quite. Think about which stat these players lead in."
