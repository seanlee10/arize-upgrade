import json
from pathlib import Path

import pytest

from arize_upgrade import cli


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, notification, reply_to=None):
        self.sent.append((notification, reply_to))
        return "ts-1"


SAMPLE = """\
# Release 11.43.0 (2026-08-13)

## Updates

* new

***

# Release 11.42.0 (2026-08-11)

## Upgrade Notes

* Pin your storage classes.
"""


@pytest.fixture
def outputs(tmp_path, monkeypatch):
    path = tmp_path / "gh_output"
    path.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    monkeypatch.setenv("RUN_URL", "https://github.com/o/r/actions/runs/1")
    return path


def read_outputs(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key] = value
    return result


def test_check_emits_the_target_version_when_newer(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 41, 0))
    monkeypatch.setattr(cli, "_in_progress", lambda: False)
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)

    assert cli.main(["check"]) == 0
    assert read_outputs(outputs)["target_version"] == "11.43.0"


def test_check_emits_empty_when_already_current(outputs, monkeypatch):
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 43, 0))
    monkeypatch.setattr(cli, "_in_progress", lambda: False)
    monkeypatch.setattr(cli, "_notifier", lambda env: RecordingNotifier())

    assert cli.main(["check"]) == 0
    assert read_outputs(outputs)["target_version"] == ""


def test_check_does_not_notify_when_already_current(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 43, 0))
    monkeypatch.setattr(cli, "_in_progress", lambda: False)
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)

    cli.main(["check"])
    assert notifier.sent == []


def test_check_skips_when_an_upgrade_is_already_running(outputs, monkeypatch):
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 41, 0))
    monkeypatch.setattr(cli, "_in_progress", lambda: True)
    monkeypatch.setattr(cli, "_notifier", lambda env: RecordingNotifier())

    assert cli.main(["check"]) == 0
    assert read_outputs(outputs)["target_version"] == ""


def test_check_fails_loudly_and_alerts_when_nothing_parses(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: "# Some Other Page\n")
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 41, 0))
    monkeypatch.setattr(cli, "_in_progress", lambda: False)
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)

    assert cli.main(["check"]) == 1
    assert notifier.sent, "a parse failure must alert the channel"
    assert notifier.sent[0][0].status == "failure"


def test_check_alerts_when_the_deployed_version_is_unknown(outputs, monkeypatch):
    from arize_upgrade.state import DeployedVersionUnknown

    notifier = RecordingNotifier()

    def raise_unknown(env):
        raise DeployedVersionUnknown("seed DEPLOYED_VERSION")

    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", raise_unknown)
    monkeypatch.setattr(cli, "_in_progress", lambda: False)
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)

    assert cli.main(["check"]) == 1
    assert "seed DEPLOYED_VERSION" in notifier.sent[0][0].body


def test_notify_detected_sends_and_emits_the_thread_ref(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_fetch_markdown", lambda url: SAMPLE)
    monkeypatch.setattr(cli, "_deployed_version", lambda env: cli.Version(11, 41, 0))
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)

    assert cli.main(["notify", "--stage", "detected", "--target", "11.43.0"]) == 0
    assert read_outputs(outputs)["thread_ref"] == "ts-1"
    assert "11.43.0" in notifier.sent[0][0].title


def test_notify_images_threads_under_the_parent(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)
    monkeypatch.setenv("PUSH_REGISTRY", "123.dkr.ecr.eu-west-1.amazonaws.com")

    code = cli.main(
        ["notify", "--stage", "images", "--target", "11.43.0", "--reply-to", "ts-1"]
    )
    assert code == 0
    assert notifier.sent[0][1] == "ts-1"


def test_notify_result_success_uses_the_app_url(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)
    monkeypatch.setenv("APP_BASE_URL", "https://arize.example.com")

    cli.main(["notify", "--stage", "result", "--target", "11.43.0", "--outcome", "success"])
    notification = notifier.sent[0][0]
    assert notification.status == "success"
    assert any(b.url == "https://arize.example.com" for b in notification.buttons)


def test_notify_result_failure_is_marked_failure(outputs, monkeypatch):
    notifier = RecordingNotifier()
    monkeypatch.setattr(cli, "_notifier", lambda env: notifier)
    monkeypatch.setenv("APP_BASE_URL", "https://arize.example.com")

    cli.main(["notify", "--stage", "result", "--target", "11.43.0", "--outcome", "failure"])
    assert notifier.sent[0][0].status == "failure"


def test_verify_bundle_succeeds_on_a_match(tmp_path, capsys):
    bundle = tmp_path / "arize-distribution-11.43.0"
    bundle.mkdir()
    (bundle / "arize.sh").write_text("#!/bin/bash\n")

    assert cli.main(["verify-bundle", "--dir", str(tmp_path), "--expect", "11.43.0"]) == 0


def test_verify_bundle_fails_on_a_mismatch(tmp_path):
    bundle = tmp_path / "arize-distribution-11.44.0"
    bundle.mkdir()
    (bundle / "arize.sh").write_text("#!/bin/bash\n")

    assert cli.main(["verify-bundle", "--dir", str(tmp_path), "--expect", "11.43.0"]) == 1


def test_record_writes_a_release(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        cli, "_record", lambda version, notes: recorded.append((version, notes))
    )
    assert cli.main(["record", "--version", "11.43.0"]) == 0
    assert recorded[0][0] == cli.Version(11, 43, 0)
