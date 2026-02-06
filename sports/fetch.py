"""
Fetch all-time leaders from Sports Reference sites.
Uses one request per leaderboard (e.g. career passing TDs) so runs stay short.
Results are written to the SQLite DB; next run uses cache (no refetch by default).
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .db import DB_PATH, get_connection, init_db

# Prefer curl_cffi to avoid 403 (mimics browser TLS). pip install curl_cffi
try:
    from curl_cffi import requests as curl_requests
    _HAS_CURL_CFFI = True
except ImportError:
    _HAS_CURL_CFFI = False

# Delay between requests to avoid rate limits (seconds)
REQUEST_DELAY = 1.2

# Browser-like headers so Sports Reference is less likely to return 403
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


# (league, stat_label, url_path) — one GET per URL
LEADERBOARD_URLS = [
    # NFL (Pro-Football-Reference)
    ("nfl", "pass_td", "https://www.pro-football-reference.com/leaders/pass_td_career.htm"),
    ("nfl", "pass_yds", "https://www.pro-football-reference.com/leaders/pass_yds_career.htm"),
    ("nfl", "rush_td", "https://www.pro-football-reference.com/leaders/rush_td_career.htm"),
    ("nfl", "rush_yds", "https://www.pro-football-reference.com/leaders/rush_yds_career.htm"),
    ("nfl", "receptions", "https://www.pro-football-reference.com/leaders/rec_career.htm"),
    # NBA (Basketball-Reference)
    ("nba", "pts", "https://www.basketball-reference.com/leaders/pts_career.html"),
    ("nba", "trb", "https://www.basketball-reference.com/leaders/trb_career.html"),
    ("nba", "ast", "https://www.basketball-reference.com/leaders/ast_career.html"),
    ("nba", "stl", "https://www.basketball-reference.com/leaders/stl_career.html"),
    ("nba", "blk", "https://www.basketball-reference.com/leaders/blk_career.html"),
    # NHL (Hockey-Reference) — path is goals_career.html not career_goals.html
    ("nhl", "goals", "https://www.hockey-reference.com/leaders/goals_career.html"),
    ("nhl", "assists", "https://www.hockey-reference.com/leaders/assists_career.html"),
    ("nhl", "points", "https://www.hockey-reference.com/leaders/points_career.html"),
]


def _session():
    if _HAS_CURL_CFFI:
        return curl_requests.Session()
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def _get(session, url: str, **kwargs):
    if _HAS_CURL_CFFI:
        return session.get(url, impersonate="chrome110", **kwargs)
    return session.get(url, **kwargs)


def _find_leaders_table(soup: BeautifulSoup) -> BeautifulSoup | None:
    """Find the main leaders table (id=leaderboard or first table with player links)."""
    table = soup.find("table", id="leaderboard")
    if table:
        return table
    for t in soup.find_all("table"):
        if t.find("a", href=re.compile(r"/players/")):
            return t
    return None


def _parse_pfr_leaders(html: str, stat_name: str) -> list[tuple[str, str, float]]:
    """Pro-Football-Reference leaders table → (player_name, ref_slug, value)."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_leaders_table(soup)
    if not table:
        return []
    body = table.find("tbody")
    if not body:
        return []
    out = []
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        # PFR: often player link in first column
        first = cells[0]
        a = first.find("a") if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        if a and a.get("href"):
            m = re.search(r"/players/[^/]+/([^./]+)\.htm", a["href"])
            if m:
                ref_slug = m.group(1)
        # Value: usually second column or next numeric
        value = 0.0
        for c in cells[1:]:
            raw = c.get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").isdigit():
                try:
                    value = float(raw)
                    break
                except ValueError:
                    pass
        if name:
            out.append((name, ref_slug, value))
    return out


def _parse_br_leaders(html: str, stat_name: str) -> list[tuple[str, str, float]]:
    """Basketball-Reference leaders table → (player_name, ref_slug, value).
    BBR uses Rank | Player | Stat columns; player link is often in 2nd cell (index 1)."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_leaders_table(soup)
    if not table:
        return []
    body = table.find("tbody")
    if not body:
        return []
    out = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        # Try cells[0] first (PFR-style), then cells[1] (BBR Rank|Player|Stat)
        player_cell = cells[0]
        a = player_cell.find("a", href=re.compile(r"/players/")) if player_cell else None
        if not a and len(cells) > 1:
            player_cell = cells[1]
            a = player_cell.find("a", href=re.compile(r"/players/")) if player_cell else None
        name = (a.get_text(strip=True) if a else (player_cell.get_text(strip=True) if player_cell else "")) or ""
        ref_slug = ""
        if a and a.get("href"):
            m = re.search(r"/players/[^/]+/([^./]+)\.html", a["href"])
            if m:
                ref_slug = m.group(1)
        value = 0.0
        for c in cells[1:]:
            raw = c.get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").isdigit():
                try:
                    value = float(raw)
                    break
                except ValueError:
                    pass
        if name:
            out.append((name, ref_slug, value))
    return out


def _parse_hr_leaders(html: str, stat_name: str) -> list[tuple[str, str, float]]:
    """Hockey-Reference leaders table → (player_name, ref_slug, value)."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_leaders_table(soup)
    if not table:
        return []
    body = table.find("tbody")
    if not body:
        return []
    out = []
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        first = cells[0]
        a = first.find("a") if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        if a and a.get("href"):
            m = re.search(r"/players/[^/]+/([^./]+)\.html", a["href"])
            if m:
                ref_slug = m.group(1)
        value = 0.0
        for c in cells[1:]:
            raw = c.get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").isdigit():
                try:
                    value = float(raw)
                    break
                except ValueError:
                    pass
        if name:
            out.append((name, ref_slug, value))
    return out


def fetch_one(session, url: str) -> str:
    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    r = _get(session, url, timeout=15, headers={"Referer": referer})
    r.raise_for_status()
    return r.text


def run_fetches(
    *,
    force: bool = False,
    delay: float = REQUEST_DELAY,
    db_path: Path | None = None,
) -> None:
    """
    Fetch each leaderboard URL once, parse, and upsert into SQLite.
    First run does ~1 request per leaderboard (small delay between). Later runs skip if DB already has data unless force=True.
    """
    db_path = db_path or DB_PATH
    init_db(get_connection(db_path))
    conn = get_connection(db_path)
    cur = conn.cursor()

    session = _session()
    for league_id, stat_name, url in LEADERBOARD_URLS:
        if not force:
            cur.execute(
                "SELECT 1 FROM career_stats cs JOIN players p ON p.id = cs.player_id WHERE p.league_id = ? AND cs.stat_name = ? LIMIT 1",
                (league_id, stat_name),
            )
            if cur.fetchone():
                continue  # already have this leaderboard
        try:
            html = fetch_one(session, url)
            time.sleep(delay)
        except Exception as e:
            print(f"Skip {league_id} {stat_name}: {e}")
            continue

        if "pro-football-reference" in url:
            rows = _parse_pfr_leaders(html, stat_name)
        elif "basketball-reference" in url:
            rows = _parse_br_leaders(html, stat_name)
        elif "hockey-reference" in url:
            rows = _parse_hr_leaders(html, stat_name)
        else:
            rows = []

        for name, ref_slug, value in rows:
            slug = ref_slug.strip() if ref_slug else None
            if slug:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND ref_slug = ?", (league_id, slug))
            else:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND name = ? LIMIT 1", (league_id, name))
            prow = cur.fetchone()
            if not prow:
                cur.execute(
                    "INSERT INTO players (id, league_id, name, ref_slug) VALUES (nextval('players_seq'), ?, ?, ?) RETURNING id",
                    (league_id, name, slug),
                )
                player_id = cur.fetchone()[0]
            else:
                player_id = prow[0]
            cur.execute(
                "INSERT INTO career_stats (player_id, stat_name, value_real, value_int) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (player_id, stat_name) DO UPDATE SET value_real = excluded.value_real, value_int = excluded.value_int",
                (player_id, stat_name, value, int(value) if value == int(value) else None),
            )
        conn.commit()
        print(f"Stored {len(rows)} rows for {league_id} {stat_name}")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Fetch all-time leaders into sports.db (cache-first).")
    p.add_argument("--force", action="store_true", help="Refetch even if DB already has data")
    p.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Seconds between requests")
    args = p.parse_args()
    run_fetches(force=args.force, delay=args.delay)


if __name__ == "__main__":
    main()
