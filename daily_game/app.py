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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from .generator import ensure_today_puzzle, load_today, generate_random_puzzle, TODAY_JSON_PATH
from .check import check_guess

app = FastAPI(title="Patternfall")

# In-memory cache for random puzzles: token -> { rule, metric_a, created_at }
# Entries older than 30 minutes are dropped when we read.
_RANDOM_PUZZLE_CACHE: dict[str, dict] = {}
_RANDOM_CACHE_TTL_SEC = 30 * 60


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


def _fallback_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Patternfall</title></head>
<body><p>Static file missing. Add daily_game/static/index.html</p></body></html>"""
