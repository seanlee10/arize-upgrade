"""Locate and version-verify a downloaded Arize distribution bundle.

get_latest.sh serves *latest only*. If a new release lands between detection
and download, the bundle will not be the one a human approved, so a version
mismatch aborts the run.
"""

from __future__ import annotations

import re
from pathlib import Path

from .versions import Version

BUNDLE_DIR_PATTERN = re.compile(r"^arize-distribution-(\d+\.\d+\.\d+)$")


class BundleNotFound(RuntimeError):
    """Raised when zero, or more than one, bundle directory is present."""


class BundleVersionMismatch(RuntimeError):
    """Raised when the downloaded bundle is not the approved version."""


def find_bundle_dir(root: Path) -> Path:
    candidates = [
        path
        for path in sorted(root.iterdir())
        if path.is_dir()
        and BUNDLE_DIR_PATTERN.match(path.name)
        and (path / "arize.sh").is_file()
    ]
    if not candidates:
        raise BundleNotFound(
            f"no arize-distribution-X.Y.Z directory containing arize.sh under {root}"
        )
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise BundleNotFound(f"found more than one bundle directory: {names}")
    return candidates[0]


def bundle_version(path: Path) -> Version:
    match = BUNDLE_DIR_PATTERN.match(path.name)
    if match is None:
        raise BundleNotFound(f"not a bundle directory name: {path.name}")
    return Version.parse(match.group(1))


def verify_bundle(root: Path, expected: Version) -> Path:
    path = find_bundle_dir(root)
    actual = bundle_version(path)
    if actual != expected:
        raise BundleVersionMismatch(
            f"downloaded bundle is {actual} but {expected} was approved; "
            "a newer release landed mid-run, aborting"
        )
    return path
