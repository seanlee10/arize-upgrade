"""Parse the Arize on-premise release notes.

The docs site serves a raw-markdown twin of every page. That is markedly more
stable than the rendered HTML, where each heading is wrapped in anchor markup
and prefixed with a U+200B zero-width space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from .versions import Version

RELEASES_URL = "https://arize.com/docs/ax/selfhosting/on-premise-releases.md"

# "# Release 11.41.0 (2026-07-31) (Maintenance)" -- the trailing suffix is optional.
_HEADING = re.compile(
    r"^# Release (\d+\.\d+\.\d+) \((\d{4}-\d{2}-\d{2})\).*$",
    re.MULTILINE,
)


class NoReleasesFound(RuntimeError):
    """Raised when the release document yields zero releases.

    This is always a hard failure. A docs redesign must never be
    indistinguishable from "no new release".
    """


@dataclass(frozen=True)
class Release:
    version: Version
    date: date
    upgrade_notes: str | None
    updates: str | None


def _section(body: str, name: str) -> str | None:
    """Extract one ``## <name>`` section, up to the next H2 or the end."""
    start = re.search(rf"^## {re.escape(name)}\s*$", body, re.MULTILINE)
    if start is None:
        return None
    rest = body[start.end() :]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    text = rest[: nxt.start()] if nxt else rest
    text = text.replace("***", "").strip()
    return text or None


def parse_releases(markdown: str) -> list[Release]:
    """Parse release entries, newest first.

    Raises:
        NoReleasesFound: if the document contains no release headings.
    """
    matches = list(_HEADING.finditer(markdown))
    if not matches:
        raise NoReleasesFound(
            "no '# Release X.Y.Z (YYYY-MM-DD)' headings found; "
            "the release document format has probably changed"
        )

    releases: list[Release] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[match.end() : end]
        releases.append(
            Release(
                version=Version.parse(match.group(1)),
                date=date.fromisoformat(match.group(2)),
                upgrade_notes=_section(body, "Upgrade Notes"),
                updates=_section(body, "Updates"),
            )
        )
    return sorted(releases, key=lambda r: r.version, reverse=True)


def _default_fetch(url: str) -> str:
    import requests

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_releases(
    url: str = RELEASES_URL,
    *,
    fetch: Callable[[str], str] | None = None,
) -> list[Release]:
    """Fetch and parse releases. ``fetch`` is injectable for tests."""
    fetcher = fetch or _default_fetch
    return parse_releases(fetcher(url))


def upgrade_notes_between(
    releases: list[Release],
    current: Version,
    target: Version,
) -> list[Release]:
    """Releases with upgrade notes in ``(current, target]``, oldest first.

    Oldest first because that is the order an operator would apply them.
    """
    selected = [
        r
        for r in releases
        if current < r.version <= target and r.upgrade_notes is not None
    ]
    return sorted(selected, key=lambda r: r.version)
