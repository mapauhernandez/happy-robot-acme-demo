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

- `certs/rootCA.pem`: the CA certificate that clients should trust.
- `certs/server.crt` (and `certs/server.pem`): the certificate you pass to Uvicorn. It includes Subject Alternative Names for
  both `localhost` and `127.0.0.1`, so browsers or CLI tools can connect with either host name without triggering a hostname
  mismatch warning.
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
  --ssl-certfile localhost-cert.pem --ssl-keyfile localhost-key.pem
```

When using HTTPS the API key header requirement is unchanged. By default the demo accepts the value
`local-dev-api-key`; set the `DEMO_API_KEY` environment variable to customize it. Requests must also provide a JSON
body containing `origin` and `equipment_type`. Example:

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-api-key" \
  -d '{"origin": "Austin, TX", "equipment_type": "Dry Van"}' \
  --cacert certs/rootCA.pem \
  https://127.0.0.1:8000/loads/match
```

Passing `--cacert certs/rootCA.pem` lets `curl` verify the certificate chain produced by the helper script. If you generated a one-off self-signed certificate instead, use `--insecure` while you test locally or import the certificate into your system trust store.

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
  -e SSL_CERTFILE=/certs/localhost-cert.pem \
  -e SSL_KEYFILE=/certs/localhost-key.pem \
  -v $(pwd)/localhost-cert.pem:/certs/localhost-cert.pem:ro \
  -v $(pwd)/localhost-key.pem:/certs/localhost-key.pem:ro \
  tiny-api
```

The container entrypoint automatically adds the correct `--ssl-*` flags to Uvicorn when both variables are supplied.
If the variables are omitted the server listens over plain HTTP.

If you generated certificates with `scripts/generate-certs.sh`, mount `certs/server.crt` and `certs/server.key` instead and have clients trust `certs/rootCA.pem` (for example, by passing `--cacert certs/rootCA.pem` to curl).

The container exposes the same FastAPI application on port `8000`. Adjust `DEMO_API_KEY` to match the credential you
intend to use for requests.
