# Sports stats DB (NFL, NBA, NHL)

All-time leaders and career stats in SQLite. Used for queries like “most touchdowns all time” or “players who played on the most NBA teams.”

## Quick start

```bash
cd /path/to/daily_game
pip install -r sports/requirements.txt
python -m sports.fetch
```

If you get **403 Forbidden** from Sports Reference, the script will use **curl_cffi** when installed (included in `sports/requirements.txt`) to mimic a real browser and avoid block.

- **First run**: Fetches one page per leaderboard (~12 requests, ~1.2s apart). Takes about 1–2 minutes total.
- **Later runs**: Skips leaderboards already in the DB. Use `--force` to refetch everything.

## Parser notes

**NBA/NHL**: Parsers updated for BBR/HR table layout. If data is incomplete: Basketball-Reference’s career leaders pages use a different table/cell structure than the parser expects. NFL and NHL work.
## Data source

One request per leaderboard to Sports Reference:

- **NFL**: Pro-Football-Reference (pass_td, pass_yds, rush_td, rush_yds, receptions)
- **NBA**: Basketball-Reference (pts, trb, ast, stl, blk)
- **NHL**: Hockey-Reference (goals, assists, points)

Results are cached in `sports/sports.duckdb`. No refetch on normal use. (DuckDB is used so the script doesn’t depend on your system’s SQLite, which can break on some macOS/conda setups.)

## DB schema

- `leagues` – nfl, nba, nhl, soccer
- `players` – league_id, name, ref_slug
- `career_stats` – player_id, stat_name, value_real/value_int
- `player_teams` – (for “most teams” style queries; populated by a separate script later)
- `teams` – team list per league

## Example queries

```bash
duckdb sports/sports.duckdb
```

Or from Python: `import duckdb; duckdb.connect("sports/sports.duckdb").execute("SELECT ...")`

```sql
-- NFL career passing TDs
SELECT p.name, cs.value_int
FROM career_stats cs
JOIN players p ON p.id = cs.player_id
WHERE p.league_id = 'nfl' AND cs.stat_name = 'pass_td'
ORDER BY cs.value_real DESC LIMIT 10;

-- NBA career points
SELECT p.name, cs.value_int
FROM career_stats cs
JOIN players p ON p.id = cs.player_id
WHERE p.league_id = 'nba' AND cs.stat_name = 'pts'
ORDER BY cs.value_real DESC LIMIT 10;
```

## Options

- `python -m sports.fetch --force` – refetch all leaderboards
- `python -m sports.fetch --delay 2` – 2s between requests (if you get rate-limited)
