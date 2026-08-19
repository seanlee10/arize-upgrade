"""Deployment state, stored as GitHub Releases tagged deployed/<version>.

Git history is the audit log; no extra infrastructure is required.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Callable, Mapping

from .versions import InvalidVersion, Version

TAG_PREFIX = "deployed/"
UPGRADE_WORKFLOW = "upgrade.yml"

# A job paused at an environment approval gate reports "waiting".
ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "requested", "pending"}


class DeployedVersionUnknown(RuntimeError):
    """Raised when the deployed version cannot be determined.

    The automation never guesses which version is on the cluster.
    """


def _default_run(argv: list[str]) -> Any:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def read_deployed_version(
    env: Mapping[str, str],
    *,
    run: Callable[..., Any] | None = None,
) -> Version:
    runner = run or _default_run
    result = runner(
        ["gh", "release", "list", "--limit", "100", "--json", "tagName"],
    )
    if result.returncode != 0:
        raise DeployedVersionUnknown(
            f"could not list GitHub releases: {getattr(result, 'stderr', '')}"
        )

    versions: list[Version] = []
    for entry in json.loads(result.stdout or "[]"):
        tag = entry.get("tagName", "")
        if not tag.startswith(TAG_PREFIX):
            continue
        try:
            versions.append(Version.parse(tag[len(TAG_PREFIX) :]))
        except InvalidVersion:
            continue

    if versions:
        return max(versions)

    bootstrap = env.get("DEPLOYED_VERSION", "").strip()
    if bootstrap:
        try:
            return Version.parse(bootstrap)
        except InvalidVersion as exc:
            raise DeployedVersionUnknown(str(exc)) from exc

    raise DeployedVersionUnknown(
        "no 'deployed/<version>' GitHub Release exists and the DEPLOYED_VERSION "
        "repository variable is unset. Seed it with the version currently on the "
        "cluster, for example: gh variable set DEPLOYED_VERSION --body 11.41.0"
    )


def record_deployment(
    version: Version,
    *,
    notes: str,
    run: Callable[..., Any] | None = None,
) -> None:
    runner = run or _default_run
    tag = f"{TAG_PREFIX}{version}"
    result = runner(
        [
            "gh",
            "release",
            "create",
            tag,
            "--title",
            f"Deployed {version}",
            "--notes",
            notes,
        ],
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"could not create release {tag}: {getattr(result, 'stderr', '')}"
        )


def upgrade_in_progress(*, run: Callable[..., Any] | None = None) -> bool:
    runner = run or _default_run
    result = runner(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            UPGRADE_WORKFLOW,
            "--limit",
            "20",
            "--json",
            "status",
        ],
    )
    if result.returncode != 0:
        # Fail safe: if we cannot tell, assume something is running rather
        # than dispatching a concurrent upgrade.
        return True
    return any(
        entry.get("status") in ACTIVE_STATUSES
        for entry in json.loads(result.stdout or "[]")
    )
