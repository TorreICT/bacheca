#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

read_env() {
    key="$1"
    default_value="$2"
    backend_env_file="$SCRIPT_DIR/.env"
    frontend_env_file="$SCRIPT_DIR/../bacheca/.env"

    eval "existing_value=\${$key:-}"
    if [ -n "$existing_value" ]; then
        printf '%s' "$existing_value"
        return
    fi

    for env_file in "$backend_env_file" "$frontend_env_file"; do
        if [ -f "$env_file" ]; then
            value=$(grep -m 1 "^$key=" "$env_file" 2>/dev/null | sed "s/^$key=//; s/^['\"]//; s/['\"]$//" || true)
            if [ -n "$value" ]; then
                printf '%s' "$value"
                return
            fi
        fi
    done

    printf '%s' "$default_value"
}

HOST=$(read_env BACHECA_DASHBOARD_HOST "0.0.0.0")
PORT=$(read_env BACHECA_DASHBOARD_PORT "8080")

cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    . "$SCRIPT_DIR/.venv/bin/activate"
fi

exec python -m uvicorn app.main:app --host "$HOST" --port "$PORT"
