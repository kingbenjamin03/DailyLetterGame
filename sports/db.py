"""
Sports stats DB (DuckDB): schema and helpers.
Uses DuckDB instead of SQLite to avoid system lib issues (e.g. conda Python + macOS).
Cache-first: fetches populate this; queries read from here (no slow fetches in normal use).
"""
from __future__ import annotations

from pathlib import Path

import duckdb

# Default DB next to this package
DB_PATH = Path(__file__).resolve().parent / "sports.duckdb"


def get_connection(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = path or DB_PATH
    return duckdb.connect(str(path))


def init_db(conn: duckdb.DuckDBPyConnection | None = None) -> None:
    conn = conn or get_connection()
    cur = conn.cursor()

    # Leagues we support
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leagues (
            id VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL
        )
    """)

    # Teams (per league)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id VARCHAR PRIMARY KEY,
            league_id VARCHAR NOT NULL,
            abbreviation VARCHAR,
            name VARCHAR,
            FOREIGN KEY (league_id) REFERENCES leagues(id)
        )
    """)

    # Players (league + name + optional ref slug for dedup; profile_path = exact path from site for links)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            league_id VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            ref_slug VARCHAR,
            profile_path VARCHAR,
            FOREIGN KEY (league_id) REFERENCES leagues(id)
        )
    """)
    try:
        cur.execute("ALTER TABLE players ADD COLUMN profile_path VARCHAR")
    except Exception:
        pass  # column may already exist
    cur.execute("CREATE SEQUENCE IF NOT EXISTS players_seq START 1")
    # Ensure we have a way to get next id (DuckDB: use nextval in INSERT)

    # Career stat totals (one row per player per stat name)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS career_stats (
            player_id INTEGER NOT NULL,
            stat_name VARCHAR NOT NULL,
            value_real DOUBLE,
            value_int BIGINT,
            PRIMARY KEY (player_id, stat_name),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    # Season stat totals (one row per player per stat per year) — e.g. "most passing TD in 2010"
    cur.execute("""
        CREATE TABLE IF NOT EXISTS season_stats (
            player_id INTEGER NOT NULL,
            stat_name VARCHAR NOT NULL,
            season_year INTEGER NOT NULL,
            value_real DOUBLE,
            value_int BIGINT,
            PRIMARY KEY (player_id, stat_name, season_year),
            FOREIGN KEY (player_id) REFERENCES players(id)
        )
    """)

    # Player–team history (for "played on most teams" etc.)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS player_teams (
            player_id INTEGER NOT NULL,
            team_id VARCHAR NOT NULL,
            season_year INTEGER,
            PRIMARY KEY (player_id, team_id, season_year),
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        )
    """)

    # Seed leagues
    for lid, lname in [("nfl", "NFL"), ("nba", "NBA"), ("nhl", "NHL"), ("soccer", "Soccer")]:
        cur.execute(
            "INSERT INTO leagues (id, name) VALUES (?, ?) ON CONFLICT (id) DO NOTHING",
            (lid, lname),
        )

    conn.commit()


def reset_db(path: Path | None = None) -> None:
    path = path or DB_PATH
    if path.exists():
        path.unlink()
    init_db(get_connection(path))
