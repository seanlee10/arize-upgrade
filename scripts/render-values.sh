#!/usr/bin/env bash
# Render config/values.template.yaml into a working values.yaml.
# Usage: scripts/render-values.sh <output-path>
#
# Never cat or log the output: it contains private keys and passwords.
set -euo pipefail

OUTPUT="${1:?usage: render-values.sh <output-path>}"
TEMPLATE="$(dirname "$0")/../config/values.template.yaml"

# No sensible default: secrets, plus identity/infrastructure values that are
# unique to this cluster. Missing any of these must fail closed and name it.
REQUIRED=(
  ARIZE_HUB_JWT
  ARIZE_CIPHER_KEY
  ARIZE_POSTGRES_PASSWORD
  ARIZE_SMTP_USER
  ARIZE_SMTP_PASSWORD
  ARIZE_GCP_SA_KEY
  ARIZE_INTERNAL_TLS_CERT
  ARIZE_INTERNAL_TLS_KEY
  ARIZE_FLIGHT_TLS_CERT
  ARIZE_FLIGHT_TLS_KEY
  ARIZE_CLUSTER_ARN
  ARIZE_REGION
  ARIZE_GAZETTE_BUCKET
  ARIZE_DRUID_BUCKET
  ARIZE_ORGANIZATION_NAME
  ARIZE_APP_BASE_URL
  ARIZE_EXP_BASE_URL
  ARIZE_RW_BUCKET_ROLE_ARN
  ARIZE_PUSH_REGISTRY
  ARIZE_GCP_PROJECT
  ARIZE_SMTP_HOST
  ARIZE_SMTP_SENDER_EMAIL
)

# Generic values that are the same for most installs. Applied when unset;
# each application is logged so a render's effective config is traceable.
# (Plain "NAME=default" entries, not an associative array, so this runs on
# bash 3.2 as well as the bash 5 used by GitHub-hosted runners.)
OPTIONAL_WITH_DEFAULT=(
  ARIZE_CLOUD=aws
  ARIZE_REPO_NAME=arize
  ARIZE_CLUSTER_SIZING=test
  ARIZE_STORAGE_CLASS_AWS_STANDARD=gp3
  ARIZE_STORAGE_CLASS_AWS_SSD=gp3
  ARIZE_SMTP_PORT=587
  ARIZE_SMTP_REQUIRE_TLS=true
  ARIZE_COLLECT_NODE_METRICS=true
  ARIZE_ZONE_AWARE=false
  ARIZE_ALYX_ENABLED=false
  ARIZE_REALTIME_USE_LATEST_OFFSET=false
  ARIZE_REALTIME_MUTABLE_CUTOVER_DATE=3000-01-01T00:00:00Z
  ARIZE_REALTIME_GLOBAL_CUTOVER_TIME=3000-01-01T00:00:00Z
  ARIZE_REALTIME_SPACE_CUTOVER_TIME=3000-01-01T00:00:00Z
  ARIZE_DATA_FABRIC_ENABLED=true
  ARIZE_DATA_FABRIC_PERMISSIONS_CHECK_ENABLED=true
  ARIZE_HISTORICAL_NODE_POOL_ENABLED=true
  ARIZE_ENABLE_CUSTOM_CODE_EVALS=true
)

missing=()
for name in "${REQUIRED[@]}"; do
  if [ -z "${!name:-}" ]; then missing+=("$name"); fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "🛑 missing required variables/secrets: ${missing[*]}" >&2
  exit 1
fi

applied_defaults=()
optional_names=()
for entry in "${OPTIONAL_WITH_DEFAULT[@]}"; do
  name="${entry%%=*}"
  default="${entry#*=}"
  optional_names+=("$name")
  if [ -z "${!name:-}" ]; then
    export "$name=$default"
    applied_defaults+=("$name=$default")
  fi
done
if [ ${#applied_defaults[@]} -gt 0 ]; then
  # Sort for stable, diffable output.
  IFS=$'\n' sorted=($(sort <<<"${applied_defaults[*]}")); unset IFS
  echo "ℹ️  applied defaults: ${sorted[*]}" >&2
fi

ALL_VARS=("${REQUIRED[@]}" "${optional_names[@]}")

# Restrict substitution to our own variables so unrelated '$' in the
# template is left alone.
substitutions=""
for name in "${ALL_VARS[@]}"; do substitutions="${substitutions}\${${name}}"; done

envsubst "$substitutions" < "$TEMPLATE" > "$OUTPUT"
chmod 600 "$OUTPUT"

if grep -qE '\$\{ARIZE_[A-Z_]+\}' "$OUTPUT"; then
  echo "🛑 unsubstituted placeholders remain in the rendered values file" >&2
  exit 1
fi

echo "✅ rendered $(wc -l < "$OUTPUT") lines to $OUTPUT"
