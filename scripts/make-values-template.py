#!/usr/bin/env python3
"""Generate config/values.template.yaml from a real values.yaml.

Replaces every secret field (SECRET_FIELDS) and every other
environment-specific config field (CONFIG_FIELDS) with a ${VAR} placeholder,
and adds the ECR settings, also templated. Run this once against the live
file; never commit the input.

SECRET_FIELDS and CONFIG_FIELDS are rewritten identically -- the only
difference between them is where the value ends up in GitHub: a
SECRET_FIELDS entry becomes a GitHub Secret, a CONFIG_FIELDS entry becomes a
GitHub (repository) Variable. The five leak gates below apply to both, with
one deliberate exception: the value-based residual-secret gate (Gate 2)
checks only SECRET_FIELDS values, not CONFIG_FIELDS values -- see the note
on that gate.

Usage: python3 scripts/make-values-template.py /path/to/values.yaml [output-path]

output-path defaults to config/values.template.yaml when omitted.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# yaml key -> environment variable used in the template. These become
# GitHub Secrets.
SECRET_FIELDS = {
    "hubJwt": "ARIZE_HUB_JWT",
    "cipherKey": "ARIZE_CIPHER_KEY",
    "postgresPassword": "ARIZE_POSTGRES_PASSWORD",
    "smtpUser": "ARIZE_SMTP_USER",
    "smtpPassword": "ARIZE_SMTP_PASSWORD",
    "multiCloudGcpServiceAccountKey": "ARIZE_GCP_SA_KEY",
    "internalEndpointsAppTlsCert": "ARIZE_INTERNAL_TLS_CERT",
    "internalEndpointsAppTlsKey": "ARIZE_INTERNAL_TLS_KEY",
    "flightTlsCert": "ARIZE_FLIGHT_TLS_CERT",
    "flightTlsKey": "ARIZE_FLIGHT_TLS_KEY",
}

# yaml key -> environment variable, for every other environment-specific
# (but non-secret) field: cluster/network identity, buckets, URLs, and the
# deployment toggles/tunables. These become GitHub (repository) Variables.
# Rewritten by exactly the same per-line logic as SECRET_FIELDS below --
# the two mappings are combined into REWRITE_FIELDS and treated
# identically there. The only place they're treated differently is Gate 2
# (residual-value check), which intentionally stays scoped to
# SECRET_FIELDS -- see the note on that gate.
CONFIG_FIELDS = {
    "clusterName": "ARIZE_CLUSTER_ARN",
    "region": "ARIZE_REGION",
    "gazetteBucket": "ARIZE_GAZETTE_BUCKET",
    "druidBucket": "ARIZE_DRUID_BUCKET",
    "organizationName": "ARIZE_ORGANIZATION_NAME",
    "clusterSizing": "ARIZE_CLUSTER_SIZING",
    "appBaseUrl": "ARIZE_APP_BASE_URL",
    "expBaseUrl": "ARIZE_EXP_BASE_URL",
    "awsServiceAccountRoleRwBucket": "ARIZE_RW_BUCKET_ROLE_ARN",
    "storageClassAwsStandard": "ARIZE_STORAGE_CLASS_AWS_STANDARD",
    "storageClassAwsSsd": "ARIZE_STORAGE_CLASS_AWS_SSD",
    "smtpHost": "ARIZE_SMTP_HOST",
    "smtpSenderEmail": "ARIZE_SMTP_SENDER_EMAIL",
    "gcpProject": "ARIZE_GCP_PROJECT",
    "cloud": "ARIZE_CLOUD",
    "collectNodeMetrics": "ARIZE_COLLECT_NODE_METRICS",
    "zoneAware": "ARIZE_ZONE_AWARE",
    "alyxEnabled": "ARIZE_ALYX_ENABLED",
    "realTimeUseLatestOffset": "ARIZE_REALTIME_USE_LATEST_OFFSET",
    "realTimeMutableCutoverDate": "ARIZE_REALTIME_MUTABLE_CUTOVER_DATE",
    "realTimeGlobalCutoverTime": "ARIZE_REALTIME_GLOBAL_CUTOVER_TIME",
    "realTimeSpaceCutoverTime": "ARIZE_REALTIME_SPACE_CUTOVER_TIME",
    "smtpPort": "ARIZE_SMTP_PORT",
    "smtpRequireTls": "ARIZE_SMTP_REQUIRE_TLS",
    "dataFabricEnabled": "ARIZE_DATA_FABRIC_ENABLED",
    "dataFabricPermissionsCheckEnabled": "ARIZE_DATA_FABRIC_PERMISSIONS_CHECK_ENABLED",
    "historicalNodePoolEnabled": "ARIZE_HISTORICAL_NODE_POOL_ENABLED",
    "enableCustomCodeEvals": "ARIZE_ENABLE_CUSTOM_CODE_EVALS",
    # pushRegistry / repoName are additions this pipeline makes -- the
    # vendor's values.yaml never defines them, so there is nothing to
    # rewrite in place. They are handled by the ECR_SETTINGS append below
    # instead of the generic per-line rewrite (see _ECR_ONLY_FIELDS), but
    # are listed here so they still appear in the completeness gate and in
    # documentation as GitHub Variables.
    "pushRegistry": "ARIZE_PUSH_REGISTRY",
    "repoName": "ARIZE_REPO_NAME",
}

ALL_FIELDS = {**SECRET_FIELDS, **CONFIG_FIELDS}

# pushRegistry/repoName are always appended fresh via ECR_SETTINGS rather
# than rewritten in place, so any pre-existing line for them in the source
# is dropped instead of templated -- see the per-line loop below.
_ECR_ONLY_FIELDS = {"pushRegistry", "repoName"}

# Fields rewritten by the generic per-line loop: everything except the
# ECR-only fields, which are handled by the drop-then-append path instead.
REWRITE_FIELDS = {k: v for k, v in ALL_FIELDS.items() if k not in _ECR_ONLY_FIELDS}

# Added so arize.sh pushes to and pulls from ECR instead of Arize's registry.
ECR_SETTINGS = f"""
# --- Private registry (added for the automated upgrade pipeline) ---
pushRegistry: "${{{CONFIG_FIELDS['pushRegistry']}}}"
repoName: "${{{CONFIG_FIELDS['repoName']}}}"
"""

# Loose presence detection: does the SOURCE mention this key at all, in any
# indentation? Used only to decide "was this key present", never to decide
# what to rewrite -- the rewrite below stays strictly anchored at line start
# so we don't accidentally template something inside a comment or a nested
# structure. Comparing "present" (loose) against what actually got
# templated (strict) is what catches formatting the strict rewrite misses.
_LOOSE = {k: re.compile(rf"^\s*{re.escape(k)}\s*:", re.MULTILINE) for k in ALL_FIELDS}

# Check 1: a single long base64-looking run on one line. 100 chars is high
# enough that an ordinary URL or identifier (which mixes in '.', ':', '-',
# and other punctuation outside this charset) essentially never reaches it
# on one line, while a real embedded credential (e.g. an unwrapped JSON key
# or JWT-shaped blob) comfortably does.
_B64_RUN = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")

# Check 2: a wrapped base64 body -- PEM bodies wrap at 64/76 columns, so no
# single line ever reaches the 100-char threshold above. A PEM body is a
# run of lines that are ENTIRELY base64; an ordinary config value (even a
# long URL) never is, because its line also carries other punctuation, a
# key name, and a colon. This matches only a line that is base64 start to
# finish; two or more such lines in a row is what actually indicates a
# wrapped credential rather than one long token that happens to sit alone
# on its own line.
_B64_LINE = re.compile(r"^\s*[A-Za-z0-9+/]{40,}={0,2}\s*$")

# Check 3: any PEM armour, not just one exact phrase -- two of the ten
# target fields are certificates, and TLS keys are commonly PKCS#1 (RSA) or
# EC, not just the generic "PRIVATE KEY" phrase.
_PEM = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?(?:PRIVATE KEY|CERTIFICATE)-----")

# Extracts a YAML key name only, for error messages. Never returns line
# content beyond a short, key-shaped token, so it cannot leak a secret --
# a block-scalar continuation line (no colon) yields a fixed, safe label.
_KEY_LABEL = re.compile(r"^\s*([A-Za-z0-9_.\-]{1,60})\s*:")


def _safe_label(line: str) -> str:
    match = _KEY_LABEL.match(line)
    return match.group(1) if match else "<continuation line, no key>"


def _placeholder_value(var: str, value_segment: str) -> str:
    """Render "${var}", preserving the source's own quoting style.

    Secrets and most config fields are quoted strings; the boolean, int,
    and timestamp toggles/tunables (e.g. collectNodeMetrics, smtpPort,
    realTimeMutableCutoverDate) are unquoted in the source, and must stay
    unquoted so YAML still parses them as their native type once envsubst
    fills in the placeholder.
    """
    stripped = value_segment.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        return f"{stripped[0]}${{{var}}}{stripped[0]}"
    return f"${{{var}}}"


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2

    source_path = Path(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) == 3 else Path("config/values.template.yaml")

    source = source_path.read_text(encoding="utf-8")

    # What the source actually contains, regardless of indentation -- the
    # honest set to compare "was this templated" against.
    present = {k for k, pattern in _LOOSE.items() if pattern.search(source)}

    replaced: set[str] = set()
    dropped_comments = 0
    original_values: dict[str, str] = {}

    lines = []
    for line in source.splitlines():
        # A commented-out credential is never useful config, and the secret-key
        # matching below only rewrites live "key:" lines — so a stale comment
        # would otherwise carry a real secret straight into the committed template.
        # Uses the same 100-char single-line threshold as check 1 below, so an
        # ordinary long comment (e.g. a URL) is not mistaken for a credential.
        if re.match(r"^#", line) and _B64_RUN.search(line):
            dropped_comments += 1
            continue

        for key, var in REWRITE_FIELDS.items():
            if re.match(rf"^{re.escape(key)}\s*:", line):
                value_segment = line.split(":", 1)[1]
                lines.append(f"{key}: {_placeholder_value(var, value_segment)}")
                replaced.add(key)
                raw = value_segment.strip().strip('"').strip("'")
                # Gate 2 (below) only makes sense for secrets: a config
                # value like a region or a boolean is expected to recur
                # elsewhere in ordinary text, so checking it would produce
                # false refusals rather than catching a real leak.
                if raw and key in SECRET_FIELDS:
                    original_values[key] = raw
                break
        else:
            # pushRegistry/repoName are always appended fresh via
            # ECR_SETTINGS (see _ECR_ONLY_FIELDS); drop any pre-existing
            # line for them so the output never has a duplicate key.
            if re.match(r"^(pushRegistry|repoName)\s*:", line):
                continue
            lines.append(line)

    rendered = "\n".join(lines).rstrip() + "\n" + ECR_SETTINGS
    rendered_lines = rendered.splitlines()

    # Self-certify, all before any file write: a half-written template that
    # a later step might commit is worse than none.

    # Gate 1: a key the source actually contains (however formatted) must
    # have ended up as a placeholder. Catches indentation/formatting the
    # strict line-start rewrite above doesn't match -- e.g. an indented
    # "  hubJwt:" line passes through untouched with its real value intact,
    # and this is the only check positioned to notice that. Matched with a
    # regex (not a fixed substring) because CONFIG_FIELDS placeholders can
    # be quoted or unquoted depending on the source's own style (see
    # _placeholder_value).
    untemplated = sorted(
        k
        for k in present
        if not re.search(
            rf'^{re.escape(k)}:\s*.*\$\{{{re.escape(ALL_FIELDS[k])}\}}',
            rendered,
            re.MULTILINE,
        )
    )
    if untemplated:
        print(
            "ERROR: refusing to write; these keys exist in the source but were not templated:",
            file=sys.stderr,
        )
        for k in untemplated:
            print(f"  {k}", file=sys.stderr)
        print(
            "(likely indented or unusually formatted — the rewrite regex is anchored at line start)",
            file=sys.stderr,
        )
        return 1

    # Gate 2: shape-based gates (below) cannot see a short, non-base64
    # secret duplicated verbatim in a stale comment or leftover line --
    # e.g. a live `smtpPassword: "hunter2"` correctly templated, alongside
    # a forgotten `# old smtpPassword: hunter2` elsewhere. This compares
    # against the actual values we just replaced, which is strictly
    # stronger than any shape heuristic. Only the key name is ever
    # printed, never the value. A floor avoids pathological matches on
    # trivial values like "true".
    #
    # Deliberately scoped to SECRET_FIELDS only (original_values is only
    # ever populated for SECRET_FIELDS keys, above). CONFIG_FIELDS values
    # are ordinary config text -- a region code, a boolean, a bucket name
    # fragment -- and are expected to recur elsewhere in a normal
    # values.yaml (e.g. a region embedded in an ARN on another line, or a
    # bucket-name prefix reused across gazette/druid buckets); extending
    # this exact-value scan to them produces false refusals on ordinary
    # config rather than catching a real leak. The shape-based gates below
    # (base64 run, wrapped body, PEM armour) still apply to everything.
    _MIN_VALUE_LEN = 8
    residual = []
    for key, value in original_values.items():
        if len(value) < _MIN_VALUE_LEN:
            continue
        for i, line in enumerate(rendered_lines, start=1):
            if value in line:
                residual.append((i, key))
                break
    if residual:
        print(
            "ERROR: refusing to write; a replaced secret's value still appears in the output:",
            file=sys.stderr,
        )
        for number, key in residual:
            print(f"  line {number}: value of {key} <REDACTED>", file=sys.stderr)
        return 1

    # Gate 3: check 1 -- a single long base64-looking run anywhere. Only a
    # safe key label is ever printed, never line content.
    single_line_leaks = [
        (i, _safe_label(line))
        for i, line in enumerate(rendered_lines, start=1)
        if _B64_RUN.search(line)
    ]
    if single_line_leaks:
        print("ERROR: refusing to write; long base64 payload survived:", file=sys.stderr)
        for number, label in single_line_leaks:
            print(f"  line {number}: {label} <REDACTED>", file=sys.stderr)
        return 1

    # Gate 4: check 2 -- a wrapped base64 body: two or more consecutive
    # lines that are base64 start to finish (see _B64_LINE above).
    wrapped_leak_line = None
    consecutive = 0
    for i, line in enumerate(rendered_lines, start=1):
        if _B64_LINE.match(line):
            consecutive += 1
            if consecutive == 2:
                wrapped_leak_line = i - 1  # first line of the run
                break
        else:
            consecutive = 0
    if wrapped_leak_line is not None:
        label = _safe_label(rendered_lines[wrapped_leak_line - 1])
        print("ERROR: refusing to write; a wrapped base64 body survived:", file=sys.stderr)
        print(f"  line {wrapped_leak_line}: {label} <REDACTED>", file=sys.stderr)
        return 1

    # Gate 5: check 3 -- no PEM armour of any kind (private key or
    # certificate), not just the one exact "BEGIN PRIVATE KEY" phrase. The
    # armour text itself is a fixed marker, never secret material, so it's
    # safe to print.
    pem_match = _PEM.search(rendered)
    if pem_match:
        print(
            f"ERROR: refusing to write; PEM armour survived: {pem_match.group(0)}",
            file=sys.stderr,
        )
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    # pushRegistry/repoName are always appended via ECR_SETTINGS regardless
    # of source content, so they're never "missing" in the sense of "no
    # placeholder added" -- exclude them from that note.
    missing = sorted(set(ALL_FIELDS) - present - _ECR_ONLY_FIELDS)
    secrets_replaced = replaced & SECRET_FIELDS.keys()
    config_replaced = (replaced & CONFIG_FIELDS.keys()) | _ECR_ONLY_FIELDS
    print(
        f"wrote {output} ({len(secrets_replaced)} secrets templated, "
        f"{len(config_replaced)} config values templated, "
        f"{dropped_comments} commented-out secret-like lines dropped)"
    )
    if missing:
        print(f"note: not present in source, no placeholder added: {missing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
