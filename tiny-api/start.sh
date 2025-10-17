#!/usr/bin/env bash
set -euo pipefail

HOST="${UVICORN_HOST:-0.0.0.0}"
PORT="${UVICORN_PORT:-8000}"
APP_IMPORT="${UVICORN_APP:-app:app}"

cmd=("uvicorn" "${APP_IMPORT}" "--host" "${HOST}" "--port" "${PORT}")

if [[ -n "${SSL_CERTFILE:-}" && -n "${SSL_KEYFILE:-}" ]]; then
  cmd+=("--ssl-certfile" "${SSL_CERTFILE}" "--ssl-keyfile" "${SSL_KEYFILE}")
fi

exec "${cmd[@]}"
