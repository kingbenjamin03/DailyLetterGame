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
from bs4 import BeautifulSoup, Comment

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

# Season (by-year) leaderboards: (league_id, season_year, url, page_type).
# 2000 onward for all major sports.
NFL_YEARS = list(range(2000, 2025))  # 2000-2024
NBA_YEARS = list(range(2000, 2025))
NHL_YEARS = list(range(2000, 2025))

def _season_urls() -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    for year in NFL_YEARS:
        out.append(("nfl", year, f"https://www.pro-football-reference.com/years/{year}/passing.htm", "pfr_passing"))
        out.append(("nfl", year, f"https://www.pro-football-reference.com/years/{year}/rushing.htm", "pfr_rushing"))
        out.append(("nfl", year, f"https://www.pro-football-reference.com/years/{year}/receiving.htm", "pfr_receiving"))
    for year in NBA_YEARS:
        out.append(("nba", year, f"https://www.basketball-reference.com/leagues/NBA_{year}_totals.html", "br_totals"))
    for year in NHL_YEARS:
        out.append(("nhl", year, f"https://www.hockey-reference.com/leagues/NHL_{year}_skaters.html", "hr_skaters"))
    return out

SEASON_LEADERBOARD_URLS: list[tuple[str, int, str, str]] = _season_urls()


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


def _uncomment_html(html: str) -> str:
    """Replace HTML comments with their inner content so commented tables become parseable."""
    # Match <!-- ... --> and replace with inner content (non-greedy, DOTALL for multiline)
    return re.sub(r"<!--(.*?)-->", r"\1", html, flags=re.DOTALL)


def _find_leaders_table(soup: BeautifulSoup, url: str = "") -> BeautifulSoup | None:
    """Find the main leaders table (id=leaderboard or first table with player links)."""
    table = soup.find("table", id="leaderboard")
    if table:
        return table
    # Basketball-Reference: table is often inside an HTML comment (JS reveals it on load)
    if "basketball-reference" in url:
        for tid in ("all_tot", "all_nba", "all_aba"):
            t = soup.find("table", id=tid)
            if t and t.find("a", href=re.compile(r"/players/")):
                return t
            div = soup.find("div", id=tid)
            if div:
                for node in div.find_all(string=True):
                    if isinstance(node, Comment):
                        inner = BeautifulSoup(str(node), "html.parser")
                        tbl = inner.find("table")
                        if tbl and tbl.find("a", href=re.compile(r"/players/")):
                            return tbl
        # Fallback: any comment on the page that contains a leaders-style table
        for node in soup.find_all(string=True):
            if isinstance(node, Comment) and "table" in str(node).lower():
                inner = BeautifulSoup(str(node), "html.parser")
                tbl = inner.find("table")
                if tbl and tbl.find("a", href=re.compile(r"/players/")):
                    return tbl
    candidates = [t for t in soup.find_all("table") if t.find("a", href=re.compile(r"/players/"))]
    if not candidates:
        return None
    # Prefer the table with the most body rows (main content)
    def row_count(t):
        body = t.find("tbody")
        return len(body.find_all("tr")) if body else 0
    return max(candidates, key=row_count)


def _parse_pfr_year_passing(html: str, season_year: int) -> list[tuple[str, str, str | None, str, float]]:
    """Parse PFR /years/YYYY/passing.htm. Returns [(name, ref_slug, profile_path, stat_name, value), ...]."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="passing")
    if not table:
        table = soup.find("table")
    if not table:
        return []
    thead = table.find("thead")
    body = table.find("tbody")
    if not thead or not body:
        return []
    header_cells = thead.find_all("th")
    headers = [c.get_text(strip=True) for c in header_cells]
    try:
        player_idx = next(i for i, h in enumerate(headers) if h == "Player")
    except StopIteration:
        return []
    try:
        td_idx = next(i for i, h in enumerate(headers) if h == "TD")
    except StopIteration:
        td_idx = None
    try:
        yds_idx = next(i for i, h in enumerate(headers) if h == "Yds")
    except StopIteration:
        yds_idx = None
    indices_needed = [i for i in (player_idx, td_idx, yds_idx) if i is not None and i >= 0]
    max_idx = max(indices_needed, default=0)
    out: list[tuple[str, str, str | None, str, float]] = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or len(cells) <= max_idx:
            continue
        first = cells[player_idx]
        a = first.find("a", href=re.compile(r"/players/")) if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.htm", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        if not name:
            continue
        def num_at(idx):
            if idx is None or idx >= len(cells):
                return None
            raw = cells[idx].get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").replace("-", "").isdigit():
                try:
                    return float(raw)
                except ValueError:
                    pass
            return None
        if td_idx is not None:
            v = num_at(td_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "pass_td", v))
        if yds_idx is not None:
            v = num_at(yds_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "pass_yds", v))
    return out


def _parse_pfr_year_rushing(html: str, season_year: int) -> list[tuple[str, str, str | None, str, float]]:
    """Parse PFR /years/YYYY/rushing.htm. Returns [(name, ref_slug, profile_path, stat_name, value), ...]."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="rushing")
    if not table:
        table = soup.find("table")
    if not table:
        return []
    thead, body = table.find("thead"), table.find("tbody")
    if not thead or not body:
        return []
    headers = [c.get_text(strip=True) for c in thead.find_all("th")]
    try:
        player_idx = next(i for i, h in enumerate(headers) if h == "Player")
    except StopIteration:
        return []
    td_idx = next((i for i, h in enumerate(headers) if h == "TD"), None)
    yds_idx = next((i for i, h in enumerate(headers) if h == "Yds"), None)
    max_idx = max(i for i in (player_idx, td_idx, yds_idx) if i is not None)
    out: list[tuple[str, str, str | None, str, float]] = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or len(cells) <= max_idx:
            continue
        first = cells[player_idx]
        a = first.find("a", href=re.compile(r"/players/")) if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.htm", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        if not name:
            continue
        def num_at(idx):
            if idx is None or idx >= len(cells):
                return None
            raw = cells[idx].get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").replace("-", "").isdigit():
                try:
                    return float(raw)
                except ValueError:
                    pass
            return None
        if td_idx is not None:
            v = num_at(td_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "rush_td", v))
        if yds_idx is not None:
            v = num_at(yds_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "rush_yds", v))
    return out


def _parse_pfr_year_receiving(html: str, season_year: int) -> list[tuple[str, str, str | None, str, float]]:
    """Parse PFR /years/YYYY/receiving.htm. Returns [(name, ref_slug, profile_path, stat_name, value), ...]."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="receiving")
    if not table:
        table = soup.find("table")
    if not table:
        return []
    thead, body = table.find("thead"), table.find("tbody")
    if not thead or not body:
        return []
    headers = [c.get_text(strip=True) for c in thead.find_all("th")]
    try:
        player_idx = next(i for i, h in enumerate(headers) if h == "Player")
    except StopIteration:
        return []
    rec_idx = next((i for i, h in enumerate(headers) if h == "Rec"), None)
    yds_idx = next((i for i, h in enumerate(headers) if h == "Yds"), None)
    td_idx = next((i for i, h in enumerate(headers) if h == "TD"), None)
    max_idx = max(i for i in (player_idx, rec_idx, yds_idx, td_idx) if i is not None)
    out: list[tuple[str, str, str | None, str, float]] = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or len(cells) <= max_idx:
            continue
        first = cells[player_idx]
        a = first.find("a", href=re.compile(r"/players/")) if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.htm", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        if not name:
            continue
        def num_at(idx):
            if idx is None or idx >= len(cells):
                return None
            raw = cells[idx].get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").replace("-", "").isdigit():
                try:
                    return float(raw)
                except ValueError:
                    pass
            return None
        if rec_idx is not None:
            v = num_at(rec_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "receptions", v))
        if yds_idx is not None:
            v = num_at(yds_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "rec_yds", v))
        if td_idx is not None:
            v = num_at(td_idx)
            if v is not None:
                out.append((name, ref_slug, profile_path, "rec_td", v))
    return out


def _parse_br_totals(html: str, season_year: int) -> list[tuple[str, str, str | None, str, float]]:
    """Parse BBR leagues/NBA_YYYY_totals.html. Returns [(name, ref_slug, profile_path, stat_name, value), ...]."""
    html_uncommented = _uncomment_html(html)
    soup = BeautifulSoup(html_uncommented, "html.parser")
    table = soup.find("table", id="totals")
    if not table:
        table = next((t for t in soup.find_all("table") if t.find("a", href=re.compile(r"/players/"))), None)
    if not table:
        return []
    thead, body = table.find("thead"), table.find("tbody")
    if not thead or not body:
        return []
    header_cells = thead.find_all("th")
    headers = [c.get_text(strip=True) for c in header_cells]
    try:
        player_idx = next(i for i, h in enumerate(headers) if h == "Player")
    except StopIteration:
        return []
    stat_cols = [("PTS", "pts"), ("TRB", "trb"), ("AST", "ast"), ("STL", "stl"), ("BLK", "blk")]
    indices = {stat_br: next((i for i, h in enumerate(headers) if h == stat_br), None) for stat_br, _ in stat_cols}
    max_idx = max(i for i in [player_idx] + list(indices.values()) if i is not None)
    out: list[tuple[str, str, str | None, str, float]] = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or len(cells) <= max_idx:
            continue
        first = cells[player_idx]
        a = first.find("a", href=re.compile(r"/players/")) if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.html", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        if not name:
            continue
        for stat_br, stat_name in stat_cols:
            idx = indices.get(stat_br)
            if idx is None:
                continue
            raw = cells[idx].get_text(strip=True).replace(",", "") if idx < len(cells) else ""
            if raw and raw.replace(".", "").replace("-", "").isdigit():
                try:
                    v = float(raw)
                    out.append((name, ref_slug, profile_path, stat_name, v))
                except ValueError:
                    pass
    return out


def _parse_hr_skaters(html: str, season_year: int) -> list[tuple[str, str, str | None, str, float]]:
    """Parse HR leagues/NHL_YYYY_skaters.html. Returns [(name, ref_slug, profile_path, stat_name, value), ...]."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="skaters")
    if not table:
        table = next((t for t in soup.find_all("table") if t.find("a", href=re.compile(r"/players/"))), None)
    if not table:
        return []
    thead, body = table.find("thead"), table.find("tbody")
    if not thead or not body:
        return []
    headers = [c.get_text(strip=True) for c in thead.find_all("th")]
    try:
        player_idx = next(i for i, h in enumerate(headers) if h == "Player")
    except StopIteration:
        return []
    stat_cols = [("G", "goals"), ("A", "assists"), ("PTS", "points")]
    indices = {s: next((i for i, h in enumerate(headers) if h == s), None) for s, _ in stat_cols}
    max_idx = max(i for i in [player_idx] + list(indices.values()) if i is not None)
    out: list[tuple[str, str, str | None, str, float]] = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells or len(cells) <= max_idx:
            continue
        first = cells[player_idx]
        a = first.find("a", href=re.compile(r"/players/")) if first else None
        name = (a.get_text(strip=True) if a else (first.get_text(strip=True) if first else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.html", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        if not name:
            continue
        for col_name, stat_name in stat_cols:
            idx = indices.get(col_name)
            if idx is None:
                continue
            raw = cells[idx].get_text(strip=True).replace(",", "") if idx < len(cells) else ""
            if raw and raw.replace(".", "").replace("-", "").isdigit():
                try:
                    v = float(raw)
                    out.append((name, ref_slug, profile_path, stat_name, v))
                except ValueError:
                    pass
    return out


def _norm_profile_path(href: str) -> str | None:
    """Return path for profile URL: /players/X/slug.ext or None."""
    if not href or not href.strip():
        return None
    h = href.strip().split("?")[0].split("#")[0]
    if h.startswith("http"):
        p = urlparse(h)
        return p.path if p.path.startswith("/") else None
    return h if h.startswith("/") else None


def _parse_pfr_leaders(html: str, stat_name: str, url: str = "") -> list[tuple[str, str, str | None, float]]:
    """Pro-Football-Reference leaders table → (player_name, ref_slug, profile_path, value)."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_leaders_table(soup, url)
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
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.htm", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
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
            out.append((name, ref_slug, profile_path, value))
    return out


def _parse_br_leaders(html: str, stat_name: str, url: str = "") -> list[tuple[str, str, str | None, float]]:
    """Basketball-Reference leaders table → (player_name, ref_slug, profile_path, value)."""
    # BBR wraps the leaders table in HTML comments; uncomment so the table is in the DOM
    html_uncommented = _uncomment_html(html)
    soup = BeautifulSoup(html_uncommented, "html.parser")
    table = _find_leaders_table(soup, url)
    if not table:
        return []
    body = table.find("tbody")
    if not body:
        return []
    out = []
    for row in body.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        a = None
        player_cell = None
        for c in cells:
            a = c.find("a", href=re.compile(r"/players/")) if c else None
            if a:
                player_cell = c
                break
        name = (a.get_text(strip=True) if a else (player_cell.get_text(strip=True) if player_cell else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.html", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        value = 0.0
        numerics = []
        for c in cells:
            raw = c.get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").isdigit():
                try:
                    numerics.append(float(raw))
                except ValueError:
                    pass
        if numerics:
            value = numerics[-1]
        if name:
            out.append((name, ref_slug, profile_path, value))
    return out


def _parse_hr_leaders(html: str, stat_name: str, url: str = "") -> list[tuple[str, str, str | None, float]]:
    """Hockey-Reference leaders table → (player_name, ref_slug, profile_path, value)."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_leaders_table(soup, url)
    if not table:
        return []
    body = table.find("tbody")
    if not body:
        return []
    out = []
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        player_cell = cells[1]
        a = player_cell.find("a", href=re.compile(r"/players/")) if player_cell else None
        name = (a.get_text(strip=True) if a else (player_cell.get_text(strip=True) if player_cell else "")) or ""
        ref_slug = ""
        profile_path = None
        if a and a.get("href"):
            href = a.get("href", "")
            m = re.search(r"/players/[^/]+/([^./]+)\.html", href)
            if m:
                ref_slug = m.group(1)
            profile_path = _norm_profile_path(href)
        value = 0.0
        for c in cells[2:]:
            raw = c.get_text(strip=True).replace(",", "")
            if raw and raw.replace(".", "").isdigit():
                try:
                    value = float(raw)
                    break
                except ValueError:
                    pass
        if name:
            out.append((name, ref_slug, profile_path, value))
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
            rows = _parse_pfr_leaders(html, stat_name, url)
        elif "basketball-reference" in url:
            rows = _parse_br_leaders(html, stat_name, url)
        elif "hockey-reference" in url:
            rows = _parse_hr_leaders(html, stat_name, url)
        else:
            rows = []

        for name, ref_slug, profile_path, value in rows:
            slug = ref_slug.strip() if ref_slug else None
            path = (profile_path or "").strip() or None
            if slug:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND ref_slug = ?", (league_id, slug))
            else:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND name = ? LIMIT 1", (league_id, name))
            prow = cur.fetchone()
            if not prow:
                cur.execute(
                    "INSERT INTO players (id, league_id, name, ref_slug, profile_path) VALUES (nextval('players_seq'), ?, ?, ?, ?) RETURNING id",
                    (league_id, name, slug, path),
                )
                player_id = cur.fetchone()[0]
            else:
                player_id = prow[0]
                if path:
                    cur.execute("UPDATE players SET profile_path = ? WHERE id = ?", (path, player_id))
            cur.execute(
                "INSERT INTO career_stats (player_id, stat_name, value_real, value_int) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (player_id, stat_name) DO UPDATE SET value_real = excluded.value_real, value_int = excluded.value_int",
                (player_id, stat_name, value, int(value) if value == int(value) else None),
            )
        conn.commit()
        print(f"Stored {len(rows)} rows for {league_id} {stat_name}")

    # Skip-stat per page_type: if we have this stat for (league, year), skip this URL
    _SEASON_SKIP_STAT = {"pfr_passing": "pass_td", "pfr_rushing": "rush_yds", "pfr_receiving": "receptions", "br_totals": "pts", "hr_skaters": "goals"}

    # Season (by-year) leaderboards
    for league_id, season_year, url, page_type in SEASON_LEADERBOARD_URLS:
        if not force:
            skip_stat = _SEASON_SKIP_STAT.get(page_type)
            if skip_stat:
                cur.execute(
                    "SELECT 1 FROM season_stats ss JOIN players p ON p.id = ss.player_id WHERE p.league_id = ? AND ss.season_year = ? AND ss.stat_name = ? LIMIT 1",
                    (league_id, season_year, skip_stat),
                )
                if cur.fetchone():
                    continue
        try:
            html = fetch_one(session, url)
            time.sleep(delay)
        except Exception as e:
            print(f"Skip season {league_id} {season_year} {page_type}: {e}")
            continue
        if page_type == "pfr_passing":
            rows = _parse_pfr_year_passing(html, season_year)
        elif page_type == "pfr_rushing":
            rows = _parse_pfr_year_rushing(html, season_year)
        elif page_type == "pfr_receiving":
            rows = _parse_pfr_year_receiving(html, season_year)
        elif page_type == "br_totals":
            rows = _parse_br_totals(html, season_year)
        elif page_type == "hr_skaters":
            rows = _parse_hr_skaters(html, season_year)
        else:
            rows = []
        for name, ref_slug, profile_path, stat_name, value in rows:
            slug = ref_slug.strip() if ref_slug else None
            path = (profile_path or "").strip() or None
            if slug:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND ref_slug = ?", (league_id, slug))
            else:
                cur.execute("SELECT id FROM players WHERE league_id = ? AND name = ? LIMIT 1", (league_id, name))
            prow = cur.fetchone()
            if not prow:
                cur.execute(
                    "INSERT INTO players (id, league_id, name, ref_slug, profile_path) VALUES (nextval('players_seq'), ?, ?, ?, ?) RETURNING id",
                    (league_id, name, slug, path),
                )
                player_id = cur.fetchone()[0]
            else:
                player_id = prow[0]
                if path:
                    cur.execute("UPDATE players SET profile_path = ? WHERE id = ?", (path, player_id))
            cur.execute(
                "INSERT INTO season_stats (player_id, stat_name, season_year, value_real, value_int) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT (player_id, stat_name, season_year) DO UPDATE SET value_real = excluded.value_real, value_int = excluded.value_int",
                (player_id, stat_name, season_year, value, int(value) if value == int(value) else None),
            )
        conn.commit()
        print(f"Stored {len(rows)} season rows for {league_id} {season_year} ({page_type})")


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Fetch all-time leaders into sports.db (cache-first).")
    p.add_argument("--force", action="store_true", help="Refetch even if DB already has data")
    p.add_argument("--delay", type=float, default=REQUEST_DELAY, help="Seconds between requests")
    args = p.parse_args()
    run_fetches(force=args.force, delay=args.delay)


if __name__ == "__main__":
    main()
