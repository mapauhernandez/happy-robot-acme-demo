#!/usr/bin/env bash
set -euo pipefail

CERT_DIR="${1:-certs}"
HOST_NAME="${HOST:-localhost}"
VALID_DAYS="${DAYS:-365}"

mkdir -p "${CERT_DIR}"
cd "${CERT_DIR}"

if [ ! -f rootCA.key ]; then
  openssl genrsa -out rootCA.key 4096 >/dev/null 2>&1
fi

if [ ! -f rootCA.pem ]; then
  openssl req -x509 -new -nodes -key rootCA.key -sha256 -days "${VALID_DAYS}" \
    -out rootCA.pem -subj "/CN=${HOST_NAME} Root CA" >/dev/null 2>&1
fi

cat > server.cnf <<CFG
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
CN = ${HOST_NAME}

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${HOST_NAME}
DNS.2 = localhost
IP.1 = 127.0.0.1
CFG

openssl genrsa -out server.key 2048 >/dev/null 2>&1
openssl req -new -key server.key -out server.csr -config server.cnf >/dev/null 2>&1
openssl x509 -req -in server.csr -CA rootCA.pem -CAkey rootCA.key -CAcreateserial \
  -out server.crt -days "${VALID_DAYS}" -sha256 -extensions req_ext -extfile server.cnf >/dev/null 2>&1

rm -f server.csr server.cnf rootCA.srl

cp server.crt server.pem
cp server.key server-key.pem

printf "Certificates generated in %s:\n" "${CERT_DIR}"
printf "  - rootCA.pem (trust this file on the client)\n"
printf "  - server.crt / server.pem (use as SSL_CERTFILE)\n"
printf "  - server.key / server-key.pem (use as SSL_KEYFILE)\n"
