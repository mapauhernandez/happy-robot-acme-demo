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

### Enabling HTTPS locally

HTTPS requires a certificate/key pair. You can generate one manually with OpenSSL (shown below) or run the helper script `scripts/generate-certs.sh`, which will create a local certificate authority and sign a server certificate for `localhost` in the `certs/` folder. The script avoids overwriting existing files so you can regenerate the server certificate without losing a trusted CA.

```bash
./scripts/generate-certs.sh
```

The script produces:

- `certs/rootCA.pem`: the CA certificate that clients should trust. It is generated with CA-specific extensions so TLS
  clients recognize it as a certificate authority.
- `certs/server.crt` (and `certs/server.pem`): the leaf certificate you pass to Uvicorn. It includes Subject Alternative
  Names for both `localhost` and `127.0.0.1`, so browsers or CLI tools can connect with either host name without
  triggering a hostname mismatch warning.
- `certs/server-fullchain.pem`: the leaf certificate followed by the CA certificate. Some servers (and older OpenSSL
  versions) expect the full chain in the presented certificate file—use this if you see trust errors while the CA is
  already installed.
- `certs/server.key` (and `certs/server-key.pem`): the corresponding private key.

If you prefer to generate certificates manually, run:

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout localhost-key.pem -out localhost-cert.pem \
  -subj "/CN=localhost"
```

Launch Uvicorn with TLS flags so the API is served over `https://`:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 \
  --ssl-certfile certs/server-fullchain.pem --ssl-keyfile certs/server.key
```

If you generated certificates with the helper script, point Uvicorn at the bundled chain (`server-fullchain.pem`) so it
serves both the leaf and CA certificate during the TLS handshake. When using HTTPS the API key header requirement is
unchanged. By default the demo accepts the value `local-dev-api-key`; set the `DEMO_API_KEY` environment variable to
customize it. Requests must also provide a JSON body containing `origin` and `equipment_type`. Example:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-api-key" \
  -d '{"origin": "Austin, TX", "equipment_type": "Dry Van"}' \
  --cacert certs/rootCA.pem \
  https://127.0.0.1:8000/loads/match
```

Passing `--cacert certs/rootCA.pem` lets `curl` verify the certificate chain produced by the helper script. If you generated a one-off self-signed certificate instead, use `--insecure` while you test locally or import the certificate into your system trust store.

### Recording negotiation events

The API also exposes `POST /loads/negotiations` for capturing negotiation analytics that will power a future dashboard. Provide the same `X-API-Key` header and supply the required fields as strings:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-api-key" \
  -d '{
        "load_accepted": "true",
        "posted_price": "2450",
        "final_price": "2575",
        "total_negotiations": "3",
        "call_sentiment": "positive",
        "commodity": "Steel"
      }' \
  http://127.0.0.1:8000/loads/negotiations
```

If the API is running with TLS enabled, use the same certificate guidance from the load-matching example and point `curl` at the HTTPS endpoint:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-api-key" \
  -d '{
        "load_accepted": "true",
        "posted_price": "2450",
        "final_price": "2575",
        "total_negotiations": "3",
        "call_sentiment": "positive",
        "commodity": "Steel"
      }' \
  --cacert certs/rootCA.pem \
  https://127.0.0.1:8000/loads/negotiations
```

Values are persisted in the `negotiation_events` table within `loads.db`, along with a server-generated UTC timestamp. The data can be queried later to populate a dashboard or analytics workflow.

### Viewing the negotiation dashboard

Run the FastAPI server (for example with `uvicorn app:app --reload`) and navigate to [`http://127.0.0.1:8000/dashboard`](http://127.0.0.1:8000/dashboard). The page loads a lightweight Chart.js dashboard that visualizes negotiation trends recorded through the API. Provide your API key in the field at the top of the page—by default the demo expects `local-dev-api-key`, which is already pre-filled for local development. Once authenticated, you can:

- Toggle between all negotiations, only accepted loads, or only declined loads.
- Review bar charts showing the average price differences, average final prices, and the total number of negotiation rounds.
- See sentiment distribution and commodity mix for the selected subset of negotiations.

The dashboard retrieves normalized data from the authenticated `GET /loads/negotiations` endpoint, so it automatically reflects new negotiation events as soon as you record them.

## Running with Docker

From this directory you can build the container image and run the API with Docker:

```bash
docker build -t tiny-api .
```

Run the container and expose the service:

```bash
docker run -it --rm -p 8000:8000 \
  -e DEMO_API_KEY=local-dev-api-key \
  tiny-api
```

### HTTPS in Docker

Mount certificates into the container and point the `start.sh` entrypoint at them via environment variables:

```bash
docker run -it --rm -p 8000:8000 \
  -e DEMO_API_KEY=local-dev-api-key \
  -e SSL_CERTFILE=/certs/server-fullchain.pem \
  -e SSL_KEYFILE=/certs/server.key \
  -v $(pwd)/certs/server-fullchain.pem:/certs/server-fullchain.pem:ro \
  -v $(pwd)/certs/server.key:/certs/server.key:ro \
  tiny-api
```

The container entrypoint automatically adds the correct `--ssl-*` flags to Uvicorn when both variables are supplied.
If the variables are omitted the server listens over plain HTTP.

If you generated certificates with `scripts/generate-certs.sh`, mount `certs/server-fullchain.pem` and `certs/server.key` and have clients trust `certs/rootCA.pem` (for example, by passing `--cacert certs/rootCA.pem` to curl).

The container exposes the same FastAPI application on port `8000`. Adjust `DEMO_API_KEY` to match the credential you
intend to use for requests.
