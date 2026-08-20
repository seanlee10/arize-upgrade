#!/usr/bin/env bash
# Render config/values.template.yaml into a working values.yaml.
# Usage: scripts/render-values.sh <output-path>
#
# Never cat or log the output: it contains private keys and passwords.
set -euo pipefail

OUTPUT="${1:?usage: render-values.sh <output-path>}"
TEMPLATE="$(dirname "$0")/../config/values.template.yaml"

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
)

missing=()
for name in "${REQUIRED[@]}"; do
  if [ -z "${!name:-}" ]; then missing+=("$name"); fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "🛑 missing required secrets: ${missing[*]}" >&2
  exit 1
fi

# Restrict substitution to our own variables so unrelated '$' in the
# template is left alone.
substitutions=""
for name in "${REQUIRED[@]}"; do substitutions="${substitutions}\${${name}}"; done

envsubst "$substitutions" < "$TEMPLATE" > "$OUTPUT"
chmod 600 "$OUTPUT"

if grep -q '\${ARIZE_' "$OUTPUT"; then
  echo "🛑 unsubstituted placeholders remain in the rendered values file" >&2
  exit 1
fi

echo "✅ rendered $(wc -l < "$OUTPUT") lines to $OUTPUT"
