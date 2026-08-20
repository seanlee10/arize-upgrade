"""Regression tests for scripts/make-values-template.py's self-certifying guard.

All source text used here is synthetic, generated in this file -- never
copied from the real values.yaml. These tests prove the generator refuses
to write a template when it can't certify the output is clean, per the
three findings raised in code review:

  1. per-key completeness must compare against what the source actually
     contains (loose match), not just what got rewritten (strict match),
     so an indented/oddly-formatted key can't sail through as "absent".
  2. the redaction path must never be able to print raw line content, even
     for a colon-less continuation line (the normal shape of a wrapped
     PEM body).
  3. leak detection must catch PEM-wrapped (64/76-column) bodies and any
     PEM armour, not just one exact "BEGIN PRIVATE KEY" phrase at a
     100-char threshold.
"""

from __future__ import annotations

import importlib.util
import random
import string
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "make-values-template.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("make_values_template", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mvt = _load_module()


def _random_blob(length: int, seed: int) -> str:
    rng = random.Random(seed)
    alphabet = string.ascii_letters + string.digits
    return "".join(rng.choice(alphabet) for _ in range(length))


def _run(monkeypatch, capsys, tmp_path, source_text: str, source_name: str = "values.yaml"):
    source_path = tmp_path / source_name
    source_path.write_text(source_text, encoding="utf-8")
    output_path = tmp_path / "out" / "values.template.yaml"

    monkeypatch.setattr(
        sys, "argv", ["make-values-template.py", str(source_path), str(output_path)]
    )
    rc = mvt.main()
    captured = capsys.readouterr()
    return rc, captured, output_path


ALL_KEYS_SOURCE = """\
hubJwt: dummy-jwt-value
cipherKey: dummy-cipher-value
postgresPassword: dummy-pg-password
smtpUser: dummy-smtp-user
smtpPassword: dummy-smtp-password
multiCloudGcpServiceAccountKey: dummy-gcp-key
internalEndpointsAppTlsCert: dummy-internal-cert
internalEndpointsAppTlsKey: dummy-internal-key
flightTlsCert: dummy-flight-cert
flightTlsKey: dummy-flight-key
otherSetting: unrelated-value
"""


def test_clean_source_all_ten_keys_writes_placeholders(monkeypatch, capsys, tmp_path):
    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, ALL_KEYS_SOURCE)

    assert rc == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    for key, var in mvt.SECRET_FIELDS.items():
        assert f'{key}: "${{{var}}}"' in content
    assert "10 secrets templated" in captured.out


def test_indented_key_is_refused_not_silently_dropped(monkeypatch, capsys, tmp_path):
    # Finding 1 repro: an indented hubJwt line never matches the strict
    # line-start rewrite. The old code reported it as "not present in
    # source" and wrote the raw value through untouched; the fix must
    # instead refuse to write anything at all.
    source = "  hubJwt: leaked-if-this-ships\nunrelatedSetting: fine\n"

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert not output_path.exists()
    assert "hubJwt" in captured.err


def test_commented_out_secret_like_line_is_dropped(monkeypatch, capsys, tmp_path):
    # Mirrors the real round-1 leak shape (line 62: an 840-char, single-line,
    # fully-alphanumeric comment) -- well over the restored 100-char
    # threshold, so it is unambiguously a credential rather than a URL.
    blob = _random_blob(110, seed=1)
    source = f"# someKey: {blob}\nplainSetting: ok\n"

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert blob not in content


def test_block_scalar_continuation_line_never_appears_in_stderr(monkeypatch, capsys, tmp_path):
    # Finding 2 repro: a colon-less continuation line (the normal shape of
    # a wrapped PEM body under a YAML block scalar) must never have its
    # content echoed back, even in the "leak detected" error message.
    #
    # A single 120-char run exceeds the restored 100-char single-line
    # threshold (check 1 / _B64_RUN) on its own, so this is caught there --
    # it does not depend on the two-consecutive-line wrapped check. Asserted
    # explicitly below so a regression that silently narrows check 1 would
    # be caught here rather than only in the wrapped-body test.
    blob = _random_blob(120, seed=2)
    source = f"someBlockScalar: |\n  {blob}\n"

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert not output_path.exists()
    assert blob[:40] not in captured.err
    assert blob[:40] not in captured.out
    assert "<continuation line, no key>" in captured.err
    assert "long base64 payload survived" in captured.err


def test_pem_wrapped_body_is_detected_via_consecutive_whole_base64_lines(
    monkeypatch, capsys, tmp_path
):
    # Finding 3 repro: PEM bodies wrap at 64/76 columns, which the
    # restored 100-char single-line threshold never sees on its own. Two
    # 64-char lines in a row are each individually under 100 chars, so
    # only the dedicated wrapped-body check (>= 2 consecutive whole-base64
    # lines) catches this -- confirmed via the distinct stderr message.
    line1 = _random_blob(64, seed=3)
    line2 = _random_blob(64, seed=4)
    source = (
        "tlsBlob: |\n"
        "  -----BEGIN CERTIFICATE-----\n"
        f"  {line1}\n"
        f"  {line2}\n"
        "  -----END CERTIFICATE-----\n"
    )

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert not output_path.exists()
    assert line1 not in captured.err
    assert line2 not in captured.err
    assert "wrapped base64 body survived" in captured.err


def test_rsa_private_key_armour_is_detected(monkeypatch, capsys, tmp_path):
    # Finding 3 repro: the literal-substring check for "BEGIN PRIVATE KEY"
    # missed PKCS#1 ("BEGIN RSA PRIVATE KEY"), the common TLS key format.
    source = "-----BEGIN RSA PRIVATE KEY-----\nplainSetting: ok\n"

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert not output_path.exists()
    assert "BEGIN RSA PRIVATE KEY" in captured.err


def test_long_url_in_a_comment_is_not_flagged_as_a_secret(monkeypatch, capsys, tmp_path):
    # Coordinator's ruling repro: a workload-identity audience URL is 100+
    # chars total and contains slashes, which are in the base64 alphabet --
    # it must not read as a credential. The comment must survive verbatim:
    # it is not a secret, and the comment-dropping regex (which also keys
    # off the single-line 100-char threshold) must not match it either,
    # since no unbroken run within it reaches 100 chars (dashes, dots, and
    # the "://" colon all break up the run).
    audience_comment = (
        "# audience: https://iam.googleapis.com/projects/123456789012"
        "/locations/global/workloadIdentityPools/my-pool-name"
        "/providers/my-provider-name"
    )
    source = f'cloud: "aws"\n{audience_comment}\n'

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc == 0
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert audience_comment in content


def test_short_secret_duplicated_in_a_comment_is_caught(monkeypatch, capsys, tmp_path):
    # Shape gates (base64 run, wrapped body, PEM armour) cannot see this:
    # the value is short, not base64-shaped, and not PEM. Only a check that
    # compares against the actual replaced value can catch a plaintext
    # secret duplicated in a stale comment.
    secret = "hunter2-actual-password"
    source = f'cloud: "aws"\nsmtpPassword: "{secret}"\n# old smtpPassword: {secret}\n'

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert not output_path.exists()


def test_the_residual_value_check_does_not_print_the_secret(monkeypatch, capsys, tmp_path):
    secret = "hunter2-actual-password"
    source = f'cloud: "aws"\nsmtpPassword: "{secret}"\n# old smtpPassword: {secret}\n'

    rc, captured, output_path = _run(monkeypatch, capsys, tmp_path, source)

    assert rc != 0
    assert secret not in captured.err
    assert secret not in captured.out
    assert "smtpPassword" in captured.err
