import json
from dataclasses import dataclass

import pytest

from arize_upgrade.state import (
    DeployedVersionUnknown,
    read_deployed_version,
    record_deployment,
    upgrade_in_progress,
)
from arize_upgrade.versions import Version


@dataclass
class FakeResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def runner(results):
    """Return a fake `run` that pops queued results and records argv."""
    calls = []
    queue = list(results)

    def run(argv, **kwargs):
        calls.append(argv)
        return queue.pop(0) if queue else FakeResult()

    run.calls = calls  # type: ignore[attr-defined]
    return run


def releases_json(*tags):
    return json.dumps([{"tagName": tag} for tag in tags])


def test_reads_the_newest_deployed_tag():
    run = runner([FakeResult(stdout=releases_json("deployed/11.41.0", "deployed/11.40.2"))])
    assert read_deployed_version({}, run=run) == Version(11, 41, 0)


def test_picks_the_highest_version_not_the_listed_order():
    run = runner([FakeResult(stdout=releases_json("deployed/11.40.2", "deployed/11.41.1"))])
    assert read_deployed_version({}, run=run) == Version(11, 41, 1)


def test_ignores_tags_without_the_prefix():
    run = runner([FakeResult(stdout=releases_json("v9.9.9", "deployed/11.41.0"))])
    assert read_deployed_version({}, run=run) == Version(11, 41, 0)


def test_falls_back_to_the_bootstrap_variable():
    run = runner([FakeResult(stdout="[]")])
    assert read_deployed_version({"DEPLOYED_VERSION": "11.41.0"}, run=run) == Version(11, 41, 0)


def test_releases_win_over_the_bootstrap_variable():
    run = runner([FakeResult(stdout=releases_json("deployed/11.42.0"))])
    got = read_deployed_version({"DEPLOYED_VERSION": "11.30.0"}, run=run)
    assert got == Version(11, 42, 0)


def test_no_releases_and_no_bootstrap_raises():
    run = runner([FakeResult(stdout="[]")])
    with pytest.raises(DeployedVersionUnknown):
        read_deployed_version({}, run=run)


def test_gh_failure_raises_rather_than_guessing():
    run = runner([FakeResult(returncode=1, stderr="gh: not authenticated")])
    with pytest.raises(DeployedVersionUnknown):
        read_deployed_version({}, run=run)


def test_record_deployment_creates_a_prefixed_tag():
    run = runner([FakeResult()])
    record_deployment(Version(11, 43, 0), notes="upgraded", run=run)
    argv = run.calls[0]
    assert "deployed/11.43.0" in argv
    assert argv[:3] == ["gh", "release", "create"]


def test_record_deployment_raises_on_failure():
    run = runner([FakeResult(returncode=1, stderr="tag exists")])
    with pytest.raises(RuntimeError):
        record_deployment(Version(11, 43, 0), notes="x", run=run)


def test_upgrade_in_progress_is_false_when_nothing_is_running():
    run = runner([FakeResult(stdout="[]")])
    assert upgrade_in_progress(run=run) is False


def test_upgrade_in_progress_is_true_for_a_running_workflow():
    run = runner([FakeResult(stdout=json.dumps([{"status": "in_progress"}]))])
    assert upgrade_in_progress(run=run) is True


def test_a_run_waiting_for_approval_counts_as_in_progress():
    # A job paused at an environment gate reports status "waiting".
    run = runner([FakeResult(stdout=json.dumps([{"status": "waiting"}]))])
    assert upgrade_in_progress(run=run) is True


def test_a_queued_run_counts_as_in_progress():
    run = runner([FakeResult(stdout=json.dumps([{"status": "queued"}]))])
    assert upgrade_in_progress(run=run) is True


def test_completed_runs_do_not_count():
    run = runner([FakeResult(stdout=json.dumps([{"status": "completed"}]))])
    assert upgrade_in_progress(run=run) is False


def test_upgrade_in_progress_fails_safe_when_gh_errors():
    # A gh outage must read as "something is running", never as "all clear" —
    # returning False here would let a second upgrade start concurrently.
    run = runner([FakeResult(returncode=1, stderr="gh: rate limited")])
    assert upgrade_in_progress(run=run) is True


def test_malformed_versions_under_the_prefix_are_skipped_not_fatal():
    run = runner([FakeResult(stdout=releases_json("deployed/garbage", "deployed/11.41.0"))])
    assert read_deployed_version({}, run=run) == Version(11, 41, 0)
