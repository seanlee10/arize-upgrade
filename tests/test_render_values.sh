#!/usr/bin/env bash
# Verifies rendering substitutes every placeholder and fails closed.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

export ARIZE_HUB_JWT=jwt ARIZE_CIPHER_KEY=cipher ARIZE_POSTGRES_PASSWORD=pg \
       ARIZE_SMTP_USER=smtpu ARIZE_SMTP_PASSWORD=smtpp ARIZE_GCP_SA_KEY=gcp \
       ARIZE_INTERNAL_TLS_CERT=ic ARIZE_INTERNAL_TLS_KEY=ik \
       ARIZE_FLIGHT_TLS_CERT=fc ARIZE_FLIGHT_TLS_KEY=fk

scripts/render-values.sh "$tmp/values.yaml"

grep -q 'hubJwt: "jwt"' "$tmp/values.yaml" || { echo "FAIL: hubJwt not substituted"; exit 1; }
grep -q 'pushRegistry:' "$tmp/values.yaml" || { echo "FAIL: pushRegistry missing"; exit 1; }
! grep -q '\${ARIZE_' "$tmp/values.yaml" || { echo "FAIL: placeholders remain"; exit 1; }

# Fails closed when a secret is absent.
( unset ARIZE_HUB_JWT; scripts/render-values.sh "$tmp/other.yaml" ) 2>/dev/null \
  && { echo "FAIL: missing secret did not fail"; exit 1; }

echo "PASS: render-values.sh"
