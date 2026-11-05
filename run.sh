#!/usr/bin/env bash
set -a
[ -f .env ] && . ./.env
PORT="${PORT:-8000}"

cleanup() {
    echo "Mematikan server api-apd pada port ${PORT}..."
    if [ -n "$UVICORN_PID" ]; then
        kill -TERM "$UVICORN_PID" 2>/dev/null || true
        for i in {1..30}; do
            kill -0 "$UVICORN_PID" 2>/dev/null || break
            sleep 0.1
        done
        kill -9 "$UVICORN_PID" 2>/dev/null || true
    fi
    fuser -k "${PORT}/tcp" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --reload &
UVICORN_PID=$!
wait "$UVICORN_PID"
