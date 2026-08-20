#!/usr/bin/env bash
# Verifies rendering substitutes every placeholder and fails closed.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

export ARIZE_HUB_JWT=jwt ARIZE_CIPHER_KEY=cipher ARIZE_POSTGRES_PASSWORD=pg \
       ARIZE_SMTP_USER=smtpu ARIZE_SMTP_PASSWORD=smtpp ARIZE_GCP_SA_KEY=gcp \
       ARIZE_INTERNAL_TLS_CERT=ic ARIZE_INTERNAL_TLS_KEY=ik \
       ARIZE_FLIGHT_TLS_CERT=fc ARIZE_FLIGHT_TLS_KEY=fk \
       ARIZE_CLUSTER_ARN="arn:aws:eks:us-east-1:123456789012:cluster/test-cluster" \
       ARIZE_REGION=us-east-1 \
       ARIZE_GAZETTE_BUCKET=test-gazette-bucket \
       ARIZE_DRUID_BUCKET=test-druid-bucket \
       ARIZE_ORGANIZATION_NAME=test-org \
       ARIZE_APP_BASE_URL=https://arize.example.com \
       ARIZE_EXP_BASE_URL=https://exp.example.com \
       ARIZE_RW_BUCKET_ROLE_ARN="arn:aws:iam::123456789012:role/test-role-rw" \
       ARIZE_PUSH_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com \
       ARIZE_GCP_PROJECT=test-gcp-project \
       ARIZE_SMTP_HOST=smtp.example.com \
       ARIZE_SMTP_SENDER_EMAIL=ops@example.com

scripts/render-values.sh "$tmp/values.yaml"

grep -q 'hubJwt: "jwt"' "$tmp/values.yaml" || { echo "FAIL: hubJwt not substituted"; exit 1; }
grep -q 'pushRegistry:' "$tmp/values.yaml" || { echo "FAIL: pushRegistry missing"; exit 1; }
grep -q 'clusterName: "arn:aws:eks:us-east-1:123456789012:cluster/test-cluster"' "$tmp/values.yaml" \
  || { echo "FAIL: clusterName not substituted"; exit 1; }
# Optional-with-default values should be applied when unset.
grep -q 'cloud: "aws"' "$tmp/values.yaml" || { echo "FAIL: cloud default not applied"; exit 1; }
grep -q 'repoName: "arize"' "$tmp/values.yaml" || { echo "FAIL: repoName default not applied"; exit 1; }
grep -q 'clusterSizing: "test"' "$tmp/values.yaml" || { echo "FAIL: clusterSizing default not applied"; exit 1; }
! grep -qE '\$\{ARIZE_[A-Z_]+\}' "$tmp/values.yaml" || { echo "FAIL: placeholders remain"; exit 1; }

# Fails closed when a required secret is absent.
( unset ARIZE_HUB_JWT; scripts/render-values.sh "$tmp/other.yaml" ) 2>/dev/null \
  && { echo "FAIL: missing secret did not fail"; exit 1; }

# Fails closed when a required identity/infrastructure value is absent.
( unset ARIZE_CLUSTER_ARN; scripts/render-values.sh "$tmp/other2.yaml" ) 2>/dev/null \
  && { echo "FAIL: missing cluster ARN did not fail"; exit 1; }

echo "PASS: render-values.sh"
