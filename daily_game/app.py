"""
Localhost frontend and API for the daily pattern game.
Run: uvicorn daily_game.app:app --reload --host 0.0.0.0
Then open http://localhost:8000
"""
from __future__ import annotations

import secrets
import time
from pathlib import Path

# Load .env if present (for OPENAI_API_KEY); optional, no extra dep required at runtime
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import urllib.request
import json

from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from .generator import ensure_today_puzzle, load_today, generate_random_puzzle, TODAY_JSON_PATH
from .check import check_guess

# Sports puzzle (optional: sports DB may be missing or empty)
try:
    from sports.game import get_today_puzzle as sports_get_today
    from sports.game import get_random_puzzle as sports_get_random
    from sports.game import check_sports_guess
    from sports.game import get_player_info as sports_get_player_info
    _SPORTS_AVAILABLE = True
except Exception:
    _SPORTS_AVAILABLE = False
    sports_get_today = sports_get_random = check_sports_guess = sports_get_player_info = None  # type: ignore

# Trivia puzzle (optional: Wikipedia API based)
try:
    from trivia.game import get_today_puzzle as trivia_get_today
    from trivia.game import get_random_puzzle as trivia_get_random
    from trivia.game import check_trivia_guess
    _TRIVIA_AVAILABLE = True
except Exception:
    _TRIVIA_AVAILABLE = False
    trivia_get_today = trivia_get_random = check_trivia_guess = None  # type: ignore

# Countries puzzle (optional: REST Countries API based)
try:
    from countries.game import get_today_puzzle as countries_get_today
    from countries.game import get_random_puzzle as countries_get_random
    from countries.game import check_countries_guess
    _COUNTRIES_AVAILABLE = True
except Exception:
    _COUNTRIES_AVAILABLE = False
    countries_get_today = countries_get_random = check_countries_guess = None  # type: ignore

# Movies puzzle (optional: curated list, no API)
try:
    from movies.game import get_today_puzzle as movies_get_today
    from movies.game import get_random_puzzle as movies_get_random
    from movies.game import check_movies_guess
    _MOVIES_AVAILABLE = True
except Exception:
    _MOVIES_AVAILABLE = False
    movies_get_today = movies_get_random = check_movies_guess = None  # type: ignore

app = FastAPI(title="Patternfall")

# In-memory cache for random puzzles: token -> { rule, metric_a, created_at }
# Entries older than 30 minutes are dropped when we read.
_RANDOM_PUZZLE_CACHE: dict[str, dict] = {}
_RANDOM_CACHE_TTL_SEC = 30 * 60

# Sports random puzzle cache: token -> { rule, league_id, stat_name, season_year?, created_at }
_SPORTS_RANDOM_CACHE: dict[str, dict] = {}

# Trivia random puzzle cache: token -> { rule, category_key, created_at }
_TRIVIA_RANDOM_CACHE: dict[str, dict] = {}

# Countries random puzzle cache: token -> { rule, category_key, created_at }
_COUNTRIES_RANDOM_CACHE: dict[str, dict] = {}

# Movies random puzzle cache: token -> { rule, category_key, created_at }
_MOVIES_RANDOM_CACHE: dict[str, dict] = {}


def _get_cached_random(token: str | None) -> dict | None:
    if not token or not token.strip():
        return None
    now = time.time()
    # Drop expired
    for k in list(_RANDOM_PUZZLE_CACHE):
        if now - _RANDOM_PUZZLE_CACHE[k].get("created_at", 0) > _RANDOM_CACHE_TTL_SEC:
            del _RANDOM_PUZZLE_CACHE[k]
    return _RANDOM_PUZZLE_CACHE.get(token.strip())

DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/"
DATAMUSE_API = "https://api.datamuse.com/words"


def _fetch_definition_free_dict(word: str):
    """Try Free Dictionary API. Returns (data, None) on success or (None, error)."""
    try:
        req = urllib.request.Request(
            DICT_API + urllib.request.quote(word, safe=""),
            headers={"User-Agent": "Patternfall/1.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        if isinstance(data, list) and len(data) > 0:
            return data, None
    except urllib.error.HTTPError:
        pass
    except Exception:
        pass
    return None, "Definition not found"


def _fetch_definition_datamuse(word: str):
    """Try Datamuse API (has many words). Returns (data, None) in our format or (None, error)."""
    try:
        url = DATAMUSE_API + "?sp=" + urllib.request.quote(word, safe="") + "&md=d"
        req = urllib.request.Request(url, headers={"User-Agent": "Patternfall/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            raw = json.loads(r.read().decode())
        if not isinstance(raw, list):
            return None, "Definition not found"
        # Find exact word match (Datamuse returns similar words too)
        for item in raw:
            if (item.get("word") or "").lower() == word.lower() and item.get("defs"):
                defs = item["defs"]
                meanings = []
                for d in defs[:6]:
                    if "\t" in d:
                        pos, _, defn = d.partition("\t")
                        if defn.strip():
                            meanings.append({
                                "partOfSpeech": pos.strip() or "n",
                                "definitions": [{"definition": defn.strip()}],
                            })
                if meanings:
                    return [{"meanings": meanings}], None
                break
    except Exception:
        pass
    return None, "Definition not found"


@app.get("/api/today")
def api_today(reveal_answer: bool = False):
    """Return today's puzzle. Optionally include the rule (answer) if reveal_answer=true."""
    try:
        data = ensure_today_puzzle()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}  # e.g. feature table not built
    if data is None:
        return {"ok": False, "error": "No puzzle available. Run: python -m daily_game.build_features then python -m daily_game.daily"}
    out = {
        "ok": True,
        "date": data["date"],
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/random")
def api_random(reveal_answer: bool = False):
    """Return a new puzzle with a different topic (for practice / refresh). Includes a token to use when checking."""
    try:
        data = generate_random_puzzle()
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    if data is None:
        return {"ok": False, "error": "Could not generate a puzzle. Try again."}
    token = secrets.token_urlsafe(16)
    _RANDOM_PUZZLE_CACHE[token] = {
        "rule": data["rule"],
        "metric_a": data.get("metric_a"),
        "created_at": time.time(),
    }
    out = {
        "ok": True,
        "date": "Random",
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "token": token,
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/random/reveal")
def api_random_reveal(token: str = ""):
    """Return the rule (answer) for a random puzzle by token. Used when user clicks Reveal on a random game."""
    cached = _get_cached_random(token)
    if not cached:
        return {"ok": False, "error": "Invalid or expired puzzle."}
    return {"ok": True, "rule": cached["rule"]}


def _get_cached_sports_random(token: str | None) -> dict | None:
    if not token or not token.strip():
        return None
    now = time.time()
    for k in list(_SPORTS_RANDOM_CACHE):
        if now - _SPORTS_RANDOM_CACHE[k].get("created_at", 0) > _RANDOM_CACHE_TTL_SEC:
            del _SPORTS_RANDOM_CACHE[k]
    return _SPORTS_RANDOM_CACHE.get(token.strip())


# --- Sports category ---

@app.get("/api/sports/today")
def api_sports_today(reveal_answer: bool = False):
    """Return today's sports puzzle (player names + rule). Requires sports DB with data."""
    if not _SPORTS_AVAILABLE or sports_get_today is None:
        return {"ok": False, "error": "Sports category is not available."}
    try:
        data = sports_get_today()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No sports puzzle available. Run: pip install -r sports/requirements.txt then python -m sports.fetch to populate the database."}
    out = {
        "ok": True,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "league_id": data.get("league_id", ""),
    }
    if data.get("season_year") is not None:
        out["season_year"] = data["season_year"]
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/sports/random")
def api_sports_random(reveal_answer: bool = False):
    """Return a random sports puzzle with a token for checking."""
    if not _SPORTS_AVAILABLE or sports_get_random is None:
        return {"ok": False, "error": "Sports category is not available."}
    try:
        data = sports_get_random()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No sports puzzle available. Run: pip install -r sports/requirements.txt then python -m sports.fetch to populate the database."}
    token = secrets.token_urlsafe(16)
    _SPORTS_RANDOM_CACHE[token] = {
        "rule": data["rule"],
        "league_id": data.get("league_id", ""),
        "stat_name": data.get("stat_name", ""),
        "season_year": data.get("season_year"),
        "created_at": time.time(),
    }
    out = {
        "ok": True,
        "date": "Random",
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "token": token,
        "league_id": data.get("league_id", ""),
    }
    if data.get("season_year") is not None:
        out["season_year"] = data["season_year"]
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/sports/random/reveal")
def api_sports_random_reveal(token: str = ""):
    """Reveal the rule for a random sports puzzle by token."""
    cached = _get_cached_sports_random(token)
    if not cached:
        return {"ok": False, "error": "Invalid or expired puzzle."}
    return {"ok": True, "rule": cached["rule"]}


@app.get("/api/sports/player")
def api_sports_player(name: str = "", league_id: str = ""):
    """Return player profile URL and photo for a name (optional league_id from current puzzle)."""
    if not _SPORTS_AVAILABLE or sports_get_player_info is None:
        return {"ok": False, "error": "Sports category is not available."}
    info = sports_get_player_info((name or "").strip(), (league_id or "").strip())
    if not info:
        return {"ok": False, "error": "Player not found."}
    return {"ok": True, "name": info["name"], "profile_url": info.get("profile_url"), "photo_url": info.get("photo_url"), "league_id": info.get("league_id", "")}


class SportsCheckRequest(BaseModel):
    guess: str = ""
    token: str = ""


@app.post("/api/sports/check")
def api_sports_check(body: SportsCheckRequest):
    """Check guess for sports puzzle. Use token if this is a random puzzle."""
    if not _SPORTS_AVAILABLE or check_sports_guess is None:
        return {"ok": False, "error": "Sports category is not available."}
    cached = _get_cached_sports_random(body.token)
    if cached is not None:
        rule = cached["rule"]
        league_id = cached.get("league_id", "")
        stat_name = cached.get("stat_name", "")
        season_year = cached.get("season_year")
    else:
        try:
            data = sports_get_today()
        except Exception:
            return {"ok": False, "error": "No puzzle available."}
        if data is None:
            return {"ok": False, "error": "No puzzle available."}
        rule = data["rule"]
        league_id = data.get("league_id", "")
        stat_name = data.get("stat_name", "")
        season_year = data.get("season_year")
    correct, message = check_sports_guess(body.guess or "", rule, league_id, stat_name, season_year)
    out = {"ok": True, "correct": correct, "message": message}
    if correct:
        out["rule"] = rule
    return out


# --- Trivia category ---

def _get_cached_trivia_random(token: str | None) -> dict | None:
    if not token or not token.strip():
        return None
    now = time.time()
    for k in list(_TRIVIA_RANDOM_CACHE):
        if now - _TRIVIA_RANDOM_CACHE[k].get("created_at", 0) > _RANDOM_CACHE_TTL_SEC:
            del _TRIVIA_RANDOM_CACHE[k]
    return _TRIVIA_RANDOM_CACHE.get(token.strip())


@app.get("/api/trivia/today")
def api_trivia_today(reveal_answer: bool = False):
    """Return today's trivia puzzle (items from a Wikipedia category)."""
    if not _TRIVIA_AVAILABLE or trivia_get_today is None:
        return {"ok": False, "error": "Trivia category is not available."}
    try:
        data = trivia_get_today()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No trivia puzzle available."}
    out = {
        "ok": True,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/trivia/random")
def api_trivia_random(reveal_answer: bool = False):
    """Return a random trivia puzzle with a token for checking."""
    if not _TRIVIA_AVAILABLE or trivia_get_random is None:
        return {"ok": False, "error": "Trivia category is not available."}
    try:
        data = trivia_get_random()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No trivia puzzle available."}
    token = secrets.token_urlsafe(16)
    _TRIVIA_RANDOM_CACHE[token] = {
        "rule": data["rule"],
        "category_key": data.get("category_key", ""),
        "created_at": time.time(),
    }
    out = {
        "ok": True,
        "date": "Random",
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "token": token,
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/trivia/random/reveal")
def api_trivia_random_reveal(token: str = ""):
    """Reveal the rule for a random trivia puzzle by token."""
    cached = _get_cached_trivia_random(token)
    if not cached:
        return {"ok": False, "error": "Invalid or expired puzzle."}
    return {"ok": True, "rule": cached["rule"]}


class TriviaCheckRequest(BaseModel):
    guess: str = ""
    token: str = ""


@app.post("/api/trivia/check")
def api_trivia_check(body: TriviaCheckRequest):
    """Check guess for trivia puzzle. Use token if this is a random puzzle."""
    if not _TRIVIA_AVAILABLE or check_trivia_guess is None:
        return {"ok": False, "error": "Trivia category is not available."}
    cached = _get_cached_trivia_random(body.token)
    if cached is not None:
        rule = cached["rule"]
        category_key = cached.get("category_key", "")
    else:
        try:
            data = trivia_get_today()
        except Exception:
            return {"ok": False, "error": "No puzzle available."}
        if data is None:
            return {"ok": False, "error": "No puzzle available."}
        rule = data["rule"]
        category_key = data.get("category_key", "")
    correct, message = check_trivia_guess(body.guess or "", rule, category_key)
    out = {"ok": True, "correct": correct, "message": message}
    if correct:
        out["rule"] = rule
    return out


# --- Countries category ---

def _get_cached_countries_random(token: str | None) -> dict | None:
    if not token or not token.strip():
        return None
    now = time.time()
    for k in list(_COUNTRIES_RANDOM_CACHE):
        if now - _COUNTRIES_RANDOM_CACHE[k].get("created_at", 0) > _RANDOM_CACHE_TTL_SEC:
            del _COUNTRIES_RANDOM_CACHE[k]
    return _COUNTRIES_RANDOM_CACHE.get(token.strip())


@app.get("/api/countries/today")
def api_countries_today(reveal_answer: bool = False):
    """Return today's countries puzzle."""
    if not _COUNTRIES_AVAILABLE or countries_get_today is None:
        return {"ok": False, "error": "Countries category is not available."}
    try:
        data = countries_get_today()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No countries puzzle available."}
    out: dict[str, Any] = {
        "ok": True,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "flags": data.get("flags", {}),
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/countries/random")
def api_countries_random(reveal_answer: bool = False):
    """Return a random countries puzzle with a token for checking."""
    if not _COUNTRIES_AVAILABLE or countries_get_random is None:
        return {"ok": False, "error": "Countries category is not available."}
    try:
        data = countries_get_random()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No countries puzzle available."}
    token = secrets.token_urlsafe(16)
    _COUNTRIES_RANDOM_CACHE[token] = {
        "rule": data["rule"],
        "category_key": data.get("category_key", ""),
        "created_at": time.time(),
    }
    out: dict[str, Any] = {
        "ok": True,
        "date": "Random",
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "flags": data.get("flags", {}),
        "token": token,
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/countries/random/reveal")
def api_countries_random_reveal(token: str = ""):
    """Reveal the rule for a random countries puzzle by token."""
    cached = _get_cached_countries_random(token)
    if not cached:
        return {"ok": False, "error": "Invalid or expired puzzle."}
    return {"ok": True, "rule": cached["rule"]}


class CountriesCheckRequest(BaseModel):
    guess: str = ""
    token: str = ""


@app.post("/api/countries/check")
def api_countries_check(body: CountriesCheckRequest):
    """Check guess for countries puzzle. Use token if this is a random puzzle."""
    if not _COUNTRIES_AVAILABLE or check_countries_guess is None:
        return {"ok": False, "error": "Countries category is not available."}
    cached = _get_cached_countries_random(body.token)
    if cached is not None:
        rule = cached["rule"]
        category_key = cached.get("category_key", "")
    else:
        try:
            data = countries_get_today()
        except Exception:
            return {"ok": False, "error": "No puzzle available."}
        if data is None:
            return {"ok": False, "error": "No puzzle available."}
        rule = data["rule"]
        category_key = data.get("category_key", "")
    correct, message = check_countries_guess(body.guess or "", rule, category_key)
    out: dict[str, Any] = {"ok": True, "correct": correct, "message": message}
    if correct:
        out["rule"] = rule
    return out


# --- Movies category ---

def _get_cached_movies_random(token: str | None) -> dict | None:
    if not token or not token.strip():
        return None
    now = time.time()
    for k in list(_MOVIES_RANDOM_CACHE):
        if now - _MOVIES_RANDOM_CACHE[k].get("created_at", 0) > _RANDOM_CACHE_TTL_SEC:
            del _MOVIES_RANDOM_CACHE[k]
    return _MOVIES_RANDOM_CACHE.get(token.strip())


@app.get("/api/movies/today")
def api_movies_today(reveal_answer: bool = False):
    """Return today's movies puzzle."""
    if not _MOVIES_AVAILABLE or movies_get_today is None:
        return {"ok": False, "error": "Movies category is not available."}
    try:
        data = movies_get_today()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No movies puzzle available."}
    out: dict[str, Any] = {
        "ok": True,
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/movies/random")
def api_movies_random(reveal_answer: bool = False):
    """Return a random movies puzzle with a token for checking."""
    if not _MOVIES_AVAILABLE or movies_get_random is None:
        return {"ok": False, "error": "Movies category is not available."}
    try:
        data = movies_get_random()
    except Exception as e:
        return {"ok": False, "error": f"Could not load puzzle: {e}"}
    if data is None:
        return {"ok": False, "error": "No movies puzzle available."}
    token = secrets.token_urlsafe(16)
    _MOVIES_RANDOM_CACHE[token] = {
        "rule": data["rule"],
        "category_key": data.get("category_key", ""),
        "created_at": time.time(),
    }
    out: dict[str, Any] = {
        "ok": True,
        "date": "Random",
        "words": data["words"],
        "hints": data["hints"],
        "difficulty": data.get("difficulty", "medium"),
        "token": token,
    }
    if reveal_answer:
        out["rule"] = data["rule"]
    return out


@app.get("/api/movies/random/reveal")
def api_movies_random_reveal(token: str = ""):
    """Reveal the rule for a random movies puzzle by token."""
    cached = _get_cached_movies_random(token)
    if not cached:
        return {"ok": False, "error": "Invalid or expired puzzle."}
    return {"ok": True, "rule": cached["rule"]}


class MoviesCheckRequest(BaseModel):
    guess: str = ""
    token: str = ""


@app.post("/api/movies/check")
def api_movies_check(body: MoviesCheckRequest):
    """Check guess for movies puzzle. Use token if this is a random puzzle."""
    if not _MOVIES_AVAILABLE or check_movies_guess is None:
        return {"ok": False, "error": "Movies category is not available."}
    cached = _get_cached_movies_random(body.token)
    if cached is not None:
        rule = cached["rule"]
        category_key = cached.get("category_key", "")
    else:
        try:
            data = movies_get_today()
        except Exception:
            return {"ok": False, "error": "No puzzle available."}
        if data is None:
            return {"ok": False, "error": "No puzzle available."}
        rule = data["rule"]
        category_key = data.get("category_key", "")
    correct, message = check_movies_guess(body.guess or "", rule, category_key)
    out: dict[str, Any] = {"ok": True, "correct": correct, "message": message}
    if correct:
        out["rule"] = rule
    return out


class CheckRequest(BaseModel):
    guess: str = ""
    token: str = ""


@app.get("/api/definition")
def api_definition(word: str = ""):
    """Fetch word definition: Free Dictionary, then plural fallback, then Datamuse."""
    word = (word or "").strip().lower()
    if not word or not word.isalpha():
        return {"ok": False, "error": "Invalid word"}
    data, err = _fetch_definition_free_dict(word)
    if data is not None:
        return {"ok": True, "data": data}
    if len(word) > 2 and word.endswith("s"):
        data, _ = _fetch_definition_free_dict(word[:-1])
        if data is not None:
            return {"ok": True, "data": data}
    data, err = _fetch_definition_datamuse(word)
    if data is not None:
        return {"ok": True, "data": data}
    return {"ok": False, "error": err or "Definition not found"}


@app.post("/api/check")
def api_check(body: CheckRequest):
    """Check the user's guess. Use token if this is a random (refresh) puzzle."""
    cached = _get_cached_random(body.token)
    if cached is not None:
        data = cached
    else:
        try:
            data = ensure_today_puzzle()
        except FileNotFoundError:
            return {"ok": False, "error": "No puzzle available."}
        if data is None:
            return {"ok": False, "error": "No puzzle available."}
    correct, message = check_guess(body.guess or "", data["rule"], data.get("metric_a"))
    out = {"ok": True, "correct": correct, "message": message}
    if correct:
        out["rule"] = data["rule"]
    return out


STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the home splash page (category picker)."""
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse(_fallback_html())


@app.get("/language", response_class=HTMLResponse)
def language():
    """Serve the Language daily pattern game."""
    html_path = STATIC_DIR / "language.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<p>Language game not found.</p>")


@app.get("/sports", response_class=HTMLResponse)
def sports():
    """Serve the Sports daily pattern game."""
    html_path = STATIC_DIR / "sports.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<p>Sports game not found.</p>")


@app.get("/trivia", response_class=HTMLResponse)
def trivia():
    """Serve the Trivia daily pattern game."""
    html_path = STATIC_DIR / "trivia.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<p>Trivia game not found.</p>")


@app.get("/movies", response_class=HTMLResponse)
def movies():
    """Serve the Movies & TV daily pattern game."""
    html_path = STATIC_DIR / "movies.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<p>Movies game not found.</p>")


def _serve_countries_html():
    """Serve the countries game static page."""
    html_path = STATIC_DIR / "countries.html"
    if html_path.exists():
        return FileResponse(html_path)
    return HTMLResponse("<p>Countries game not found.</p>", status_code=404)


@app.get("/countries", response_class=HTMLResponse)
def countries():
    """Serve the Countries daily pattern game."""
    return _serve_countries_html()


@app.get("/countries/", response_class=HTMLResponse)
def countries_trailing_slash():
    """Serve the Countries game (trailing slash)."""
    return _serve_countries_html()


@app.get("/api/debug/routes")
def api_debug_routes():
    """Return whether this app has the countries route (to confirm you're running the right server)."""
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    return {"ok": True, "has_countries": "/countries" in routes, "routes": routes}


def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Patternfall</title></head>
<body><p>Static file missing. Add daily_game/static/index.html</p></body></html>"""
