# Tiny API

This directory hosts a minimal FastAPI application that provides load matching data for carriers.

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The SQLite database with sample load data is created automatically the first time the application runs.
It now includes at least one illustrative load for every U.S. state so the matcher always has
geographically diverse options to choose from.

## Running the API

Start the development server with Uvicorn:

```bash
uvicorn app:app --reload
```

The matching endpoint requires an API key sent via the `X-API-Key` header. By default the demo accepts the value
`local-dev-api-key`; set the `DEMO_API_KEY` environment variable to customize it. Requests must also provide a JSON
body containing `origin` and `equipment_type`. Example:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-api-key" \
  -d '{"origin": "Austin, TX", "equipment_type": "Dry Van"}' \
  http://127.0.0.1:8000/loads/match
```

The server returns a single load from the database that departs from the same state and uses the requested equipment when possible.

## Running with Docker

From this directory you can build the container image and run the API with Docker:

```bash
docker build -t tiny-api .
docker run -it --rm -p 8000:8000 -e DEMO_API_KEY=local-dev-api-key tiny-api
```

The container exposes the same FastAPI application on port `8000`. Adjust `DEMO_API_KEY` to match the credential you
intend to use for requests.
