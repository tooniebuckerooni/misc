#!/bin/sh
# Runs one or more trading loops (background) + the dashboard (foreground) in one container.
# PIPELINES is a comma list of strategy:timeframe, each getting its own isolated pipeline/DB.
# Handy for single-machine hosts (Fly.io). For a VPS you can instead use docker-compose.yml.
set -eu

PIPELINES="${PIPELINES:-meanrev:1d}"   # e.g. "meanrev:1d,ict:4h"
POLL="${POLL:-3600}"
PORT="${PORT:-8501}"

# Default to paper. Live requires BOT_MODE=live AND real trade-only keys — a deliberate choice.
if [ "${BOT_MODE:-paper}" = "live" ]; then
    RUN_CMD="live --yes"
    echo "entrypoint: LIVE trading (real orders, capped)"
else
    RUN_CMD="paper"
    echo "entrypoint: PAPER (no real orders)"
fi

# One-time fresh start: wipe old pipeline state so everything re-inits at STARTING_CAPITAL.
# Self-disables via a sentinel so normal restarts NEVER wipe your paper history.
if [ "${RESET_ON_BOOT:-0}" != "0" ] && [ ! -f /app/data/.reset_done ]; then
    echo "entrypoint: one-time fresh start — clearing pipeline state"
    rm -f /app/data/*.db /app/data/*.db-wal /app/data/*.db-shm
    mkdir -p /app/data && touch /app/data/.reset_done
fi

# Launch a resilient loop per pipeline (restarts itself if it exits).
OLD_IFS="$IFS"; IFS=','
for spec in $PIPELINES; do
    strat="${spec%%:*}"
    tf="${spec##*:}"
    echo "entrypoint: starting pipeline '$strat' @ $tf"
    (
        while true; do
            python -m src.cli $RUN_CMD --strategy "$strat" --timeframe "$tf" \
                --pipeline "$strat" --poll "$POLL" || echo "loop $strat exited ($?), restart in 30s"
            sleep 30
        done
    ) &
done
IFS="$OLD_IFS"

# Dashboard in the foreground (keeps the container alive; serves the mobile link, fleet view).
exec streamlit run src/app/dashboard.py \
    --server.port "$PORT" --server.address 0.0.0.0 --server.headless true
