"""
Sports daily puzzle: pick a leaderboard (league + stat), return top player names as "words"
and a human-readable rule. Uses sports DB (DuckDB).
"""
from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path

from .db import DB_PATH, get_connection, init_db

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
MIN_PLAYERS = 4

# TODO(data): Some scraped leaderboards have numeric "names" (e.g. rank stored as name).
# Filtering them out here; fix parsers/fetch to avoid storing numbers as player names.


def _is_valid_player_name(s: str) -> bool:
    """False if the string is empty or purely numeric (so we never show numbers as puzzle words)."""
    t = (s or "").strip()
    if not t:
        return False
    return not t.replace(".", "").replace("-", "").isdigit()


def _get_rule_and_accepted(league_id: str, stat_name: str, season_year: int | None) -> tuple[str, list[str]]:
    """Rule text and accepted guess phrases for (league_id, stat_name) and optional season_year."""
    base_rule, base_accepted = SPORT_RULES.get((league_id, stat_name), (f"{league_id.upper()} career {stat_name}", []))
    if season_year is None:
        return base_rule, base_accepted
    rule = f"{base_rule} in {season_year}"
    accepted = [p + f" {season_year}" for p in base_accepted] + [f"in {season_year}", str(season_year)]
    return rule, accepted


def _available_leaderboards(conn) -> list[tuple[str, str, int | None]]:
    """Return list of (league_id, stat_name, season_year) with at least MIN_PLAYERS valid-name rows."""
    cur = conn.cursor()
    out: list[tuple[str, str, int | None]] = []
    # Exclude leaderboards where player "name" is purely numeric (bad data)
    cur.execute("""
        SELECT p.league_id, cs.stat_name
        FROM career_stats cs
        JOIN players p ON p.id = cs.player_id
        WHERE NOT regexp_matches(TRIM(COALESCE(p.name, '')), '^[0-9.\\-]+$')
        GROUP BY p.league_id, cs.stat_name
        HAVING COUNT(*) >= ?
    """, (MIN_PLAYERS,))
    for row in cur.fetchall():
        out.append((row[0], row[1], None))
    cur.execute("""
        SELECT p.league_id, ss.stat_name, ss.season_year
        FROM season_stats ss
        JOIN players p ON p.id = ss.player_id
        WHERE NOT regexp_matches(TRIM(COALESCE(p.name, '')), '^[0-9.\\-]+$')
        GROUP BY p.league_id, ss.stat_name, ss.season_year
        HAVING COUNT(*) >= ?
    """, (MIN_PLAYERS,))
    for row in cur.fetchall():
        out.append((row[0], row[1], row[2]))
    return out


def _get_top_players(conn, league_id: str, stat_name: str, season_year: int | None = None, n: int = DEFAULT_NUM_PLAYERS) -> list[str]:
    """Return top N player names (excluding purely numeric names). Fetches extra rows to skip bad data."""
    cur = conn.cursor()
    limit = max(n * 3, 50)  # fetch extra so we can filter out numeric "names"
    if season_year is None:
        cur.execute("""
            SELECT p.name
            FROM career_stats cs
            JOIN players p ON p.id = cs.player_id
            WHERE p.league_id = ? AND cs.stat_name = ?
            ORDER BY COALESCE(cs.value_real, cs.value_int, 0) DESC
            LIMIT ?
        """, (league_id, stat_name, limit))
    else:
        cur.execute("""
            SELECT p.name
            FROM season_stats ss
            JOIN players p ON p.id = ss.player_id
            WHERE p.league_id = ? AND ss.stat_name = ? AND ss.season_year = ?
            ORDER BY COALESCE(ss.value_real, ss.value_int, 0) DESC
            LIMIT ?
        """, (league_id, stat_name, season_year, limit))
    names: list[str] = []
    for row in cur.fetchall():
        val = row[0] if row else None
        if val is not None:
            s = str(val).strip()
            if s and _is_valid_player_name(s):
                names.append(s)
                if len(names) >= n:
                    break
    return names[:n]


def _hints_for(league_id: str, stat_name: str, season_year: int | None = None) -> list[str]:
    """Three hints for this leaderboard."""
    rule, _ = _get_rule_and_accepted(league_id, stat_name, season_year)
    league_upper = league_id.upper()
    year_bit = f" in {season_year}" if season_year else ""
    if league_id == "nfl":
        return [
            f"These are {league_upper} players.",
            "They're ranked by a single stat" + (" for that season." if year_bit else " (career)."),
            rule,
        ]
    if league_id == "nba":
        return [
            f"These are {league_upper} players.",
            "Think " + (f"leaders for that season." if year_bit else "all-time career leaderboards."),
            rule,
        ]
    if league_id == "nhl":
        return [
            f"These are {league_upper} players.",
            "They're among the leaders in one stat" + (" for that year." if year_bit else "."),
            rule,
        ]
    return [
        f"These are {league_upper} players.",
        "They're stat leaders" + (" for that season." if year_bit else "."),
        rule,
    ]


def get_today_puzzle(db_path: Path | None = None) -> dict | None:
    """
    Deterministic puzzle for today: seed by date, pick one leaderboard, return
    { words, rule, hints, difficulty, league_id, stat_name, season_year }.
    """
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return None
    init_db(get_connection(db_path))
    conn = get_connection(db_path)
    available = _available_leaderboards(conn)
    if not available:
        return None
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rng = random.Random(today)
    league_id, stat_name, season_year = rng.choice(available)
    return _build_puzzle(conn, league_id, stat_name, season_year)


def get_random_puzzle(db_path: Path | None = None) -> dict | None:
    """Random puzzle (different leaderboard each time)."""
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return None
    init_db(get_connection(db_path))
    conn = get_connection(db_path)
    available = _available_leaderboards(conn)
    if not available:
        return None
    league_id, stat_name, season_year = random.choice(available)
    return _build_puzzle(conn, league_id, stat_name, season_year)


def _build_puzzle(conn, league_id: str, stat_name: str, season_year: int | None = None) -> dict | None:
    words = _get_top_players(conn, league_id, stat_name, season_year=season_year, n=DEFAULT_NUM_PLAYERS)
    if len(words) < MIN_PLAYERS:
        return None
    rule, _ = _get_rule_and_accepted(league_id, stat_name, season_year)
    hints = _hints_for(league_id, stat_name, season_year)
    result: dict = {
        "words": words,
        "rule": rule,
        "hints": hints,
        "difficulty": "medium",
        "league_id": league_id,
        "stat_name": stat_name,
    }
    if season_year is not None:
        result["season_year"] = season_year
    return result


def get_player_info(name: str, league_id: str = "", db_path: Path | None = None) -> dict | None:
    """
    Look up a player by name (and optional league_id). Returns
    { name, profile_url, photo_url, league_id } or None if not found.
    """
    name = (name or "").strip()
    if not name:
        return None
    db_path = db_path or DB_PATH
    if not db_path.exists():
        return None
    init_db(get_connection(db_path))
    conn = get_connection(db_path)
    cur = conn.cursor()
    if league_id:
        cur.execute(
            "SELECT p.name, p.ref_slug, p.league_id, p.profile_path FROM players p WHERE p.league_id = ? AND LOWER(TRIM(p.name)) = LOWER(?) LIMIT 1",
            (league_id, name),
        )
    else:
        cur.execute(
            "SELECT p.name, p.ref_slug, p.league_id, p.profile_path FROM players p WHERE LOWER(TRIM(p.name)) = LOWER(?) LIMIT 1",
            (name,),
        )
    row = cur.fetchone()
    if not row:
        return None
    pname, ref_slug, lid = row[0], row[1], row[2]
    # profile_path is optional 4th column (for existing DBs it may not exist)
    profile_path = row[3] if len(row) > 3 else None
    slug = (ref_slug or "").strip()
    path = (profile_path or "").strip()
    profile_url = ""
    photo_url = ""
    if path and path.startswith("/"):
        bases = {"nfl": "https://www.pro-football-reference.com", "nba": "https://www.basketball-reference.com", "nhl": "https://www.hockey-reference.com"}
        profile_url = (bases.get(lid) or "").rstrip("/") + path
    if not profile_url and slug:
        letter = slug[0].lower()
        if lid == "nfl":
            profile_url = f"https://www.pro-football-reference.com/players/{letter.upper()}/{slug}.htm"
            photo_url = f"https://www.pro-football-reference.com/req/202106291/images/headshots/{slug.upper()}.jpg"
        elif lid == "nba":
            profile_url = f"https://www.basketball-reference.com/players/{letter}/{slug}.html"
            photo_url = f"https://cdn.basketball-reference.com/headshots/{slug}.png"
        elif lid == "nhl":
            profile_url = f"https://www.hockey-reference.com/players/{letter}/{slug}.html"
            photo_url = f"https://www.hockey-reference.com/req/202106291/images/headshots/{slug.upper()}.jpg"
    return {
        "name": pname,
        "profile_url": profile_url or None,
        "photo_url": photo_url or None,
        "league_id": lid,
    }


def check_sports_guess(
    guess: str, rule: str, league_id: str = "", stat_name: str = "", season_year: int | None = None
) -> tuple[bool, str]:
    """
    Check user guess against the puzzle rule. Uses keyword/phrase matching.
    Returns (correct, message).
    """
    g = (guess or "").strip().lower()
    if not g:
        return False, "Type your guess first."
    _, accepted = _get_rule_and_accepted(league_id, stat_name, season_year)
    # Normalize: collapse spaces, remove extra punctuation
    normalized = " ".join(g.split())
    for phrase in accepted:
        if phrase.lower() in normalized or normalized in phrase.lower():
            return True, "Correct!"
    # Also accept the exact rule (shortened)
    rule_lower = rule.lower()
    if rule_lower in normalized or normalized in rule_lower:
        return True, "Correct!"
    # Partial: if they said the stat or league, give a nudge
    if league_id and league_id in normalized and stat_name and stat_name.replace("_", " ") in normalized:
        return False, "Right league and stat idea—try wording it like the answer (e.g. 'NFL career passing touchdowns' or '... in 2010')."
    return False, "Not quite. Think about which stat these players lead in (and which year, if it's a season puzzle)."
