"""Command line entry points invoked by the GitHub Actions workflows.

Exit codes are the contract with the workflows:
  0 -- success, or nothing to do
  1 -- hard failure the workflow must surface
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Mapping

from . import messages
from .bundle import BundleNotFound, BundleVersionMismatch, verify_bundle
from .notify.base import Notifier
from .notify.factory import build_notifier
from .releases import (
    RELEASES_URL,
    NoReleasesFound,
    parse_releases,
    upgrade_notes_between,
)
from .state import (
    DeployedVersionUnknown,
    read_deployed_version,
    record_deployment,
    upgrade_in_progress,
)
from .versions import Version

# Indirection seams so tests can substitute network, git, and chat.


def _fetch_markdown(url: str) -> str:
    # Thin seam over releases._default_fetch so tests can monkeypatch the
    # network without duplicating the HTTP call in two modules.
    from .releases import _default_fetch

    return _default_fetch(url)


def _deployed_version(env: Mapping[str, str]) -> Version:
    return read_deployed_version(env)


def _in_progress() -> bool:
    return upgrade_in_progress()


def _notifier(env: Mapping[str, str]) -> Notifier:
    return build_notifier(env)


def _record(version: Version, notes: str) -> None:
    record_deployment(version, notes=notes)


def _emit(key: str, value: str) -> None:
    """Write a step output for the workflow to branch on."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        print(f"{key}={value}")
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def _run_url() -> str:
    return os.environ.get("RUN_URL", "")


def _cmd_check(_: argparse.Namespace) -> int:
    env = os.environ
    notifier = _notifier(env)

    try:
        current = _deployed_version(env)
    except DeployedVersionUnknown as exc:
        notifier.send(
            messages.alert("Arize upgrade check could not run", str(exc), _run_url())
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        releases = parse_releases(_fetch_markdown(RELEASES_URL))
    except NoReleasesFound as exc:
        notifier.send(
            messages.alert(
                "Arize release page could not be parsed", str(exc), _run_url()
            )
        )
        print(f"error: {exc}", file=sys.stderr)
        return 1

    latest = releases[0].version
    if latest <= current:
        print(f"up to date: deployed {current}, latest {latest}")
        _emit("target_version", "")
        return 0

    if _in_progress():
        print("an upgrade run is already active; skipping")
        _emit("target_version", "")
        return 0

    print(f"new version available: {current} -> {latest}")
    _emit("target_version", str(latest))
    return 0


def _cmd_notify(args: argparse.Namespace) -> int:
    env = os.environ
    notifier = _notifier(env)
    target = Version.parse(args.target)
    run_url = _run_url()

    if args.stage == "detected":
        releases = parse_releases(_fetch_markdown(RELEASES_URL))
        current = _deployed_version(env)
        notes = upgrade_notes_between(releases, current, target)
        thread = notifier.send(messages.detected(current, target, notes, run_url))
    elif args.stage == "images":
        registry = env.get("PUSH_REGISTRY", "the private registry")
        thread = notifier.send(
            messages.images_pushed(target, registry, run_url), reply_to=args.reply_to
        )
    else:  # result
        succeeded = args.outcome == "success"
        app_url = env.get("APP_BASE_URL", "")
        thread = notifier.send(
            messages.result(target, succeeded, app_url, run_url),
            reply_to=args.reply_to,
        )

    _emit("thread_ref", thread or "")
    return 0


def _cmd_verify_bundle(args: argparse.Namespace) -> int:
    try:
        path = verify_bundle(Path(args.dir), Version.parse(args.expect))
    except (BundleNotFound, BundleVersionMismatch) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"bundle verified: {path}")
    _emit("bundle_dir", str(path))
    return 0


def _cmd_record(args: argparse.Namespace) -> int:
    version = Version.parse(args.version)
    _record(version, args.notes or f"Upgraded to {version}. {_run_url()}")
    print(f"recorded deployment of {version}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arize-upgrade")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="detect a newer release")
    check.set_defaults(func=_cmd_check)

    notify = sub.add_parser("notify", help="send a stage notification")
    notify.add_argument(
        "--stage", required=True, choices=["detected", "images", "result"]
    )
    notify.add_argument("--target", required=True)
    notify.add_argument("--reply-to", default=None)
    notify.add_argument("--outcome", choices=["success", "failure"], default="failure")
    notify.set_defaults(func=_cmd_notify)

    verify = sub.add_parser("verify-bundle", help="check the downloaded bundle version")
    verify.add_argument("--dir", required=True)
    verify.add_argument("--expect", required=True)
    verify.set_defaults(func=_cmd_verify_bundle)

    record = sub.add_parser("record", help="record a successful deployment")
    record.add_argument("--version", required=True)
    record.add_argument("--notes", default=None)
    record.set_defaults(func=_cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
