#!/usr/bin/env bash
# Render build script: install deps and pre-build feature table + initial puzzle
set -o errexit

# Download word list into data/ (Render has no /usr/share/dict/words
# and no write access to /usr/share)
mkdir -p data
if [ ! -f data/words.txt ]; then
    curl -fsSL "https://raw.githubusercontent.com/eneko/data-repository/master/data/words.txt" \
        -o data/words.txt
fi
export WORD_LIST="data/words.txt"

pip install --upgrade pip
pip install -r requirements.txt
pip install -r sports/requirements.txt

# Build the word feature table (one-time, cached in data/)
python -m daily_game.build_features

# Generate today's puzzle so the first request is fast
python -m daily_game.daily
