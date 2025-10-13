# HappyRobot Carrier API

A tiny FastAPI JSON service used by the HappyRobot voice agent to verify carriers, search demo loads, negotiate counter offers, and log inbound calls.

## Features

- Carrier verification via FMCSA QCMobile API.
- Load board search backed by a local JSON dataset.
- Simple counter-offer negotiation helper.
- Append-only call logging to JSON Lines file.
- Static API key authentication with health check bypass.

## Getting Started

### Requirements

- Python 3.11+
- `pip`

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Copy the example file and edit with real secrets:

```bash
cp .env.example .env
```

Required variables:

- `APP_API_KEY`: API key expected in the `x-api-key` header for all authenticated endpoints.
- `FMCSA_WEBKEY`: Web key issued by FMCSA for the QCMobile API.

The app loads variables from `.env` automatically at startup.

### Running Locally

```bash
uvicorn app.main:app --reload
```

The server listens on `http://127.0.0.1:8000` by default. Use the API key in the request header `x-api-key` when calling authenticated endpoints.

### Example Requests

Health check (no auth):

```bash
curl http://127.0.0.1:8000/health
```

Carrier verification:

```bash
curl \
  -H "x-api-key: $APP_API_KEY" \
  "http://127.0.0.1:8000/verify_fmcsa?mc=123456"
```

Load search:

```bash
curl \
  -H "x-api-key: $APP_API_KEY" \
  "http://127.0.0.1:8000/loads/search?equipment_type=Dry%20Van&origin=Chicago"
```

Negotiate counter offer:

```bash
curl \
  -H "Content-Type: application/json" \
  -H "x-api-key: $APP_API_KEY" \
  -d '{"listed_rate": 2000, "counter_offer": 2300}' \
  http://127.0.0.1:8000/negotiate
```

Log a call transcript:

```bash
curl \
  -H "Content-Type: application/json" \
  -H "x-api-key: $APP_API_KEY" \
  -d '{"caller":"ACME","summary":"Asked about load LV-1001"}' \
  http://127.0.0.1:8000/calls/log
```

### Docker

Build the container:

```bash
docker build -t happyrobot-api .
```

Run the container:

```bash
docker run \
  -p 8000:8000 \
  -e APP_API_KEY=$APP_API_KEY \
  -e FMCSA_WEBKEY=$FMCSA_WEBKEY \
  happyrobot-api
```

### Security Notes

- All business endpoints require the shared secret sent via the `x-api-key` header.
- Always protect the `.env` file and avoid committing real keys to source control.
- Rotate API keys periodically and prefer running the service behind HTTPS in production.

## Project Structure

```
app/
  main.py             # FastAPI application and routes
  services/
    fmcsa.py          # FMCSA client wrapper
    loads.py          # Load search helpers
  utils/
    auth.py           # API key middleware
  data/
    loads.json        # Sample load dataset
    .gitignore        # Excludes call log file
```

The call log is written to `app/data/calls.log.jsonl` as newline-delimited JSON entries.
