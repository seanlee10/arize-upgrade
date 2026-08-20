#!/usr/bin/env python3
"""Generate config/values.template.yaml from a real values.yaml.

Replaces every secret field with a ${VAR} placeholder and adds the ECR
settings. Run this once against the live file; never commit the input.

Usage: python3 scripts/make-values-template.py /path/to/values.yaml
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# yaml key -> environment variable used in the template
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

# Added so arize.sh pushes to and pulls from ECR instead of Arize's registry.
ECR_SETTINGS = """
# --- Private registry (added for the automated upgrade pipeline) ---
pushRegistry: "<aws-account-id>.dkr.ecr.<region>.amazonaws.com"
repoName: "arize"
"""


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    source = Path(sys.argv[1]).read_text(encoding="utf-8")
    replaced: set[str] = set()
    dropped_comments = 0

    lines = []
    for line in source.splitlines():
        # A commented-out credential is never useful config, and the secret-key
        # matching below only rewrites live "key:" lines — so a stale comment
        # would otherwise carry a real secret straight into the committed template.
        if re.match(r"^#.*[A-Za-z0-9+/]{100,}", line):
            dropped_comments += 1
            continue

        for key, var in SECRET_FIELDS.items():
            if re.match(rf"^{re.escape(key)}\s*:", line):
                lines.append(f'{key}: "${{{var}}}"')
                replaced.add(key)
                break
        else:
            # Drop any pre-existing registry keys; ECR_SETTINGS supplies them.
            if re.match(r"^(pushRegistry|repoName)\s*:", line):
                continue
            lines.append(line)

    rendered = "\n".join(lines).rstrip() + "\n" + ECR_SETTINGS

    # Self-certify: refuse to write a template that still carries a
    # long base64-looking payload anywhere. A half-written template that a
    # later step might commit is worse than none, so this check runs before
    # the file is ever opened for writing.
    leaks = [
        (i, line.split(":", 1)[0][:60])
        for i, line in enumerate(rendered.splitlines(), start=1)
        if re.search(r"[A-Za-z0-9+/]{100,}={0,2}", line)
    ]
    if leaks:
        print("ERROR: refusing to write; long base64 payload survived:", file=sys.stderr)
        for number, prefix in leaks:
            print(f"  line {number}: {prefix} <REDACTED>", file=sys.stderr)
        return 1

    if "BEGIN PRIVATE KEY" in rendered:
        print("ERROR: refusing to write; a private key marker survived", file=sys.stderr)
        return 1

    output = Path("config/values.template.yaml")
    output.parent.mkdir(exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    missing = set(SECRET_FIELDS) - replaced
    print(
        f"wrote {output} ({len(replaced)} secrets templated, "
        f"{dropped_comments} commented-out secret-like lines dropped)"
    )
    if missing:
        print(f"note: not present in source, no placeholder added: {sorted(missing)}")

    leaked = [k for k in SECRET_FIELDS if f'{k}: "${{' not in rendered]
    if leaked and not missing:
        print(f"ERROR: these keys were not templated: {leaked}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
