#!/usr/bin/env bash
set -euo pipefail

API_KEY="${DEMO_API_KEY:-local-dev-api-key}"
HOST="${TINY_API_HOST:-http://127.0.0.1:8000}"

read -r -d '' PAYLOAD <<'JSON'
{
  "load_accepted": "true",
  "posted_price": "1500",
  "final_price": "1800",
  "total_negotiations": "3",
  "call_sentiment": "Positive",
  "commodity": "Steel"
}
JSON

curl -v \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${API_KEY}" \
  -d "${PAYLOAD}" \
  "${HOST}/negotiations"
