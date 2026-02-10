#!/usr/bin/env bash
# Render build script: install deps and pre-build feature table + initial puzzle
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
pip install -r sports/requirements.txt

# Build the word feature table (one-time, cached in data/)
python -m daily_game.build_features

# Generate today's puzzle so the first request is fast
python -m daily_game.daily
