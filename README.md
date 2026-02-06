# Patternfall — Language Anomaly Engine

Generates a new "why are these words like this?" puzzle every day from word lists and English-language statistics. No hand-designed puzzles: a **pattern factory** that finds statistical outliers under constraints.

## Pipeline

1. **Feature vectors** — Every word gets metrics: length, entropy, vowel ratio, letter repetition, bigram weirdness, etc.
2. **Pattern templates** — Reusable rules (extreme outliers, constrained extremes, ratio anomalies) that *discover* rules from the feature table.
3. **Pattern scoring (PQS)** — Outlier strength + coherence + guessability − obscurity → only publish above threshold.
4. **Daily generator** — Pick template, generate candidates, score, select best, avoid recent repeats.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate  # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Build feature table (first run; downloads Norvig count_1w for real corpus frequency)
python -m daily_game.build_features

# Generate today's pattern (writes data/today.json for the frontend)
python -m daily_game.daily

# Run the localhost frontend
uvicorn daily_game.app:app --reload --host 127.0.0.1 --port 8000
# Open http://localhost:8000 (home) → click Language to play
```

## AI guess matching (optional)

The **Check** button first uses keyword/phrase matching. If that doesn’t match and you set an OpenAI API key, the app will call the API once per check to decide if the guess is semantically equivalent to the rule (so e.g. “the vowels are spread unevenly” can count as correct for “Words with highest vowel_spacing_std”).

**1. Get an API key**  
Create one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (you need an OpenAI account).

**2. Install the client** (already in `requirements.txt`):
```bash
pip install openai
```

**3. Set the key when you run the server**

- **Option A — export in the shell (recommended for local dev):**
  ```bash
  export OPENAI_API_KEY=sk-your-actual-key-here
  uvicorn daily_game.app:app --reload --host 127.0.0.1 --port 8000
  ```

- **Option B — inline (one-off):**
  ```bash
  OPENAI_API_KEY=sk-your-key uvicorn daily_game.app:app --reload --host 127.0.0.1 --port 8000
  ```

- **Option C — use a `.env` file (do not commit it):**  
  Copy the example and add your key:
  ```bash
  cp .env.example .env
  # Edit .env and set OPENAI_API_KEY=sk-your-actual-key
  ```
  The app loads `.env` automatically when you run `uvicorn` (via `python-dotenv` in `requirements.txt`). Just start the server as usual; no need to `export` in the shell.

**4. Confirm it’s on**  
With the key set, wrong keyword-only guesses will still get an AI check. If the API fails (e.g. bad key or rate limit), the user sees: “Not quite — try the hints or rephrase. (AI check unavailable.)”

**Model used:** `gpt-4o-mini` (cheap and fast). You can change it in `daily_game/check.py` in `_ai_semantic_match()`.

## Layout

- `daily_game/` — package
  - `words.py` — load and filter word list
  - `corpus.py` — real corpus frequency (Norvig count_1w, optional download)
  - `features.py` — compute per-word metrics
  - `patterns.py` — pattern templates (outliers, constrained, ratio)
  - `scoring.py` — PQS, difficulty band, filters
  - `hints.py` — generate 3 hints per pattern
  - `generator.py` — daily pipeline, today.json, used-pattern store
  - `build_features.py` — CLI to build/cache feature table
  - `daily.py` — CLI to emit today’s pattern
  - `app.py` — FastAPI app (home + /language)
  - `static/index.html` — home splash (categories: Language, Sports, Media, Countries, Music)
  - `static/language.html` — Language game UI (words, hints, guess, reveal)
- `data/` — feature table, count_1w, today.json, used_patterns (gitignored)

## v1 metrics (10)

length, unique_letters, entropy, max_letter_frequency, vowel_ratio, corpus_frequency (proxy), vowel_spacing_std, alphabetic_order_score, bigram_probability (internal), edit_density

## v1 templates (3)

- **Extreme outliers** — e.g. words with absurd letter repetition or ultra-low entropy.
- **Constrained extremes** — extreme on one metric subject to a human-friendly constraint (e.g. unique_letters ≥ 6).
- **Ratio anomalies** — two metrics behave oddly together (e.g. long words with very few unique letters).
