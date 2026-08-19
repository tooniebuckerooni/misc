#!/bin/sh
# Runs BOTH the trading loop (background) and the dashboard (foreground) in one container.
# Handy for single-machine hosts (e.g. Fly.io) where both share one volume. For a VPS you can
# instead use docker-compose.yml, which runs them as two independently-restarting services.
set -eu

STRATEGY="${STRATEGY:-meanrev}"
TIMEFRAME="${TIMEFRAME:-1d}"
PIPELINE="${PIPELINE:-$STRATEGY}"
POLL="${POLL:-3600}"
PORT="${PORT:-8501}"

# Default to paper. Live requires BOT_MODE=live AND real trade-only keys — a deliberate choice.
if [ "${BOT_MODE:-paper}" = "live" ]; then
    RUN_CMD="live --yes"
    echo "entrypoint: starting LIVE trading loop (real orders, capped)"
else
    RUN_CMD="paper"
    echo "entrypoint: starting PAPER loop (no real orders)"
fi

# Trading loop in the background; if it exits, log it (dashboard keeps serving so you can see state).
(
    while true; do
        python -m src.cli $RUN_CMD --strategy "$STRATEGY" --timeframe "$TIMEFRAME" \
            --pipeline "$PIPELINE" --poll "$POLL" || echo "loop exited ($?), restarting in 30s"
        sleep 30
    done
) &

# Dashboard in the foreground (keeps the container alive, serves the mobile link).
exec streamlit run src/app/dashboard.py \
    --server.port "$PORT" --server.address 0.0.0.0 --server.headless true
