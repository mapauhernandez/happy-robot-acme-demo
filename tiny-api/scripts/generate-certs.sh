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
  cat > rootCA.cnf <<CFG
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_ca

[dn]
CN = ${HOST_NAME} Local Dev Root CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical, CA:true, pathlen:0
keyUsage = critical, digitalSignature, cRLSign, keyCertSign
CFG

  openssl req -x509 -new -nodes -key rootCA.key -sha256 -days "${VALID_DAYS}" \
    -out rootCA.pem -config rootCA.cnf -extensions v3_ca >/dev/null 2>&1
  rm -f rootCA.cnf
fi

cat > server.cnf <<CFG
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = v3_req
distinguished_name = dn

[dn]
CN = ${HOST_NAME}

[v3_req]
subjectAltName = @alt_names
extendedKeyUsage = serverAuth
keyUsage = digitalSignature, keyEncipherment

[alt_names]
DNS.1 = ${HOST_NAME}
DNS.2 = localhost
IP.1 = 127.0.0.1
CFG

openssl genrsa -out server.key 2048 >/dev/null 2>&1
openssl req -new -key server.key -out server.csr -config server.cnf >/dev/null 2>&1
openssl x509 -req -in server.csr -CA rootCA.pem -CAkey rootCA.key -CAcreateserial \
  -out server.crt -days "${VALID_DAYS}" -sha256 -extensions v3_req -extfile server.cnf >/dev/null 2>&1

rm -f server.csr server.cnf rootCA.srl

cp server.crt server.pem
cp server.key server-key.pem
cat server.crt rootCA.pem > server-fullchain.pem

printf "Certificates generated in %s:\n" "${CERT_DIR}"
printf "  - rootCA.pem (trust this file on the client)\n"
printf "  - server.crt / server.pem (leaf certificate)\n"
printf "  - server.key / server-key.pem (use as SSL_KEYFILE)\n"
printf "  - server-fullchain.pem (bundle certificate plus CA for servers that expect the chain)\n"
