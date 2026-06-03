#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

read_env() {
    key="$1"
    default_value="$2"
    env_file="$SCRIPT_DIR/.env"

    eval "existing_value=\${$key:-}"
    if [ -n "$existing_value" ]; then
        printf '%s' "$existing_value"
        return
    fi

    if [ -f "$env_file" ]; then
        value=$(grep -m 1 "^$key=" "$env_file" 2>/dev/null | sed "s/^$key=//; s/^['\"]//; s/['\"]$//" || true)
        if [ -n "$value" ]; then
            printf '%s' "$value"
            return
        fi
    fi

    printf '%s' "$default_value"
}

HOST=$(read_env BACHECA_DASHBOARD_HOST "0.0.0.0")
PORT=$(read_env BACHECA_DASHBOARD_PORT "8080")

cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    . "$SCRIPT_DIR/.venv/bin/activate"
fi

# Control which services to start (1/true to start, otherwise no)
START_BACKEND=$(read_env START_BACKEND "1")
START_BOT=$(read_env START_BOT "1")
# Python module to run for the bot (module path for -m)
BOT_MODULE=$(read_env BACHECA_BOT_MODULE "telegram_bot")

backend_pid=""
bot_pid=""

start_backend() {
    echo "Starting backend: uvicorn app.main:app on $HOST:$PORT"
    python -m uvicorn app.main:app --host "$HOST" --port "$PORT" &
    backend_pid=$!
}

start_bot() {
    echo "Starting bot: python -m $BOT_MODULE"
    python -m "$BOT_MODULE" &
    bot_pid=$!
}

kill_children() {
    echo "Stopping child processes..."
    if [ -n "${backend_pid:-}" ] && kill -0 "$backend_pid" 2>/dev/null; then
        kill "$backend_pid" 2>/dev/null || true
    fi
    if [ -n "${bot_pid:-}" ] && kill -0 "$bot_pid" 2>/dev/null; then
        kill "$bot_pid" 2>/dev/null || true
    fi
}

trap 'kill_children; exit 0' INT TERM

if [ "$START_BACKEND" = "1" ] || [ "$START_BACKEND" = "true" ]; then
    start_backend
fi
if [ "$START_BOT" = "1" ] || [ "$START_BOT" = "true" ]; then
    start_bot
fi

if [ -z "${backend_pid:-}" ] && [ -z "${bot_pid:-}" ]; then
    echo "Nothing to start (both START_BACKEND and START_BOT are disabled)."
    exit 0
fi

# If both are running, monitor and shut down the other when one exits.
wait_exit_status=0
if [ -n "${backend_pid:-}" ] && [ -n "${bot_pid:-}" ]; then
    while true; do
        if ! kill -0 "$backend_pid" 2>/dev/null; then
            echo "Backend exited; shutting down bot"
            kill_children
            wait "$bot_pid" 2>/dev/null || true
            wait "$backend_pid" 2>/dev/null || true
            break
        fi
        if ! kill -0 "$bot_pid" 2>/dev/null; then
            echo "Bot exited; shutting down backend"
            kill_children
            wait "$backend_pid" 2>/dev/null || true
            wait "$bot_pid" 2>/dev/null || true
            break
        fi
        sleep 1
    done
else
    if [ -n "${backend_pid:-}" ]; then
        wait "$backend_pid" || wait_exit_status=$?
    fi
    if [ -n "${bot_pid:-}" ]; then
        wait "$bot_pid" || wait_exit_status=$?
    fi
fi

exit $wait_exit_status
