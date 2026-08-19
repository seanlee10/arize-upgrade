# Arize Auto-Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub repo that detects new Arize self-hosted releases daily, gets human approval in chat twice, moves the release's images into Amazon ECR, upgrades the EKS cluster, and reports the result.

**Architecture:** Two GitHub Actions workflows (`check-release.yml` on cron, `upgrade.yml` with two GitHub Environment approval gates) drive a Python package that holds all non-trivial logic — release parsing, version comparison, deployment state, and a pluggable Slack/Teams notifier. The workflows shell out to the vendor's `arize.sh` for the actual image transfer and install.

**Tech Stack:** Python 3.11, `requests`, `pytest`, GitHub Actions, `actionlint`, `envsubst`, AWS CLI, Docker, Helm/kubectl (via `arize.sh`).

**Spec:** `docs/superpowers/specs/2026-08-20-arize-auto-upgrade-design.md`

## Global Constraints

- **Python 3.11+.** Runtime dependency is `requests` only. Test dependency is `pytest` only.
- **Package root is `src/arize_upgrade/`**, installed as an editable package exposing the console script `arize-upgrade`.
- **Never commit `values.yaml`.** It is in `.gitignore`. Only `config/values.template.yaml` (placeholders) is tracked.
- **Never log rendered values.** Steps that render or consume `values.yaml` must not `cat` it or pass `-v` to `arize.sh`.
- **`arize.sh` is always invoked with `-y -q`.** `-y` sets `INTERACTIVE=false`, which is the only thing that skips `the push step()`'s blocking `read` prompt. `-q` suppresses the banner.
- **All shell steps use `set -euo pipefail`.**
- **Release source of truth:** `https://arize.com/docs/ax/selfhosting/on-premise-releases.md`
- **Distribution source:** `https://ch.hub.arize.com/dist/get_latest.sh` (Bearer JWT; serves *latest only*).
- **Zero parsed releases is always a hard failure**, never a silent "no new version".
- **`docs/` must stay tracked.** The user's `~/.gitignore_global:11` ignores `docs`; the repo `.gitignore` already carries `!docs/` to override it. Do not remove that line.
- **Repo variable `NOTIFY_PROVIDER`** is `slack` or `teams`. Exactly one is active; an unknown value raises.

---

### Task 1: Project scaffolding and version arithmetic

**Files:**
- Create: `pyproject.toml`
- Create: `src/arize_upgrade/__init__.py`
- Create: `src/arize_upgrade/versions.py`
- Test: `tests/test_versions.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Version` (frozen, ordered dataclass with `major: int`, `minor: int`, `patch: int`; `Version.parse(str) -> Version`; `str(Version) -> "11.43.0"`), and `InvalidVersion(ValueError)`. Every later task uses `Version` as the currency for release identity.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "arize-upgrade"
version = "0.1.0"
description = "Automated upgrade pipeline for self-hosted Arize AX"
requires-python = ">=3.11"
dependencies = ["requests>=2.31"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
arize-upgrade = "arize_upgrade.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_versions.py`:

```python
import pytest

from arize_upgrade.versions import InvalidVersion, Version


def test_parse_extracts_components():
    assert Version.parse("11.43.0") == Version(11, 43, 0)


def test_str_roundtrips():
    assert str(Version.parse("11.41.1")) == "11.41.1"


def test_ordering_is_numeric_not_lexicographic():
    # Lexicographically "11.9.0" > "11.40.0"; numerically it is not.
    assert Version.parse("11.9.0") < Version.parse("11.40.0")


def test_patch_versions_order():
    assert Version.parse("11.41.0") < Version.parse("11.41.1")


def test_equal_versions_are_not_newer():
    assert not (Version.parse("11.41.0") > Version.parse("11.41.0"))


def test_sorting_descending_gives_newest_first():
    versions = [Version.parse(v) for v in ("11.40.2", "11.43.0", "11.41.1")]
    assert max(versions) == Version.parse("11.43.0")


@pytest.mark.parametrize("bad", ["11.43", "v11.43.0", "11.43.0-rc1", "", "eleven"])
def test_invalid_versions_raise(bad):
    with pytest.raises(InvalidVersion):
        Version.parse(bad)
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
python3 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
.venv/bin/pytest tests/test_versions.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.versions'`.

- [ ] **Step 4: Write the implementation**

Create `src/arize_upgrade/__init__.py` as an empty file. Create `src/arize_upgrade/versions.py`:

```python
"""Semantic version parsing and comparison for Arize releases."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class InvalidVersion(ValueError):
    """Raised when a string is not a bare X.Y.Z version."""


@dataclass(frozen=True, order=True)
class Version:
    """An Arize release version.

    ``order=True`` compares by field declaration order, which gives correct
    numeric semver ordering: 11.9.0 < 11.40.0.
    """

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "Version":
        match = _PATTERN.match(text.strip())
        if match is None:
            raise InvalidVersion(f"not a valid X.Y.Z version: {text!r}")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_versions.py -q
```

Expected: PASS, 10 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/arize_upgrade/__init__.py src/arize_upgrade/versions.py tests/test_versions.py
git commit -m "feat: add Version parsing and numeric semver ordering"
```

---

### Task 2: Release notes parser

**Files:**
- Create: `src/arize_upgrade/releases.py`
- Create: `tests/fixtures/releases.md` (downloaded)
- Test: `tests/test_releases.py`

**Interfaces:**
- Consumes: `Version` from Task 1.
- Produces:
  - `RELEASES_URL: str`
  - `Release` (frozen dataclass: `version: Version`, `date: datetime.date`, `upgrade_notes: str | None`, `updates: str | None`)
  - `NoReleasesFound(RuntimeError)`
  - `parse_releases(markdown: str) -> list[Release]` — newest first
  - `fetch_releases(url: str = RELEASES_URL, *, fetch=None) -> list[Release]`
  - `upgrade_notes_between(releases: list[Release], current: Version, target: Version) -> list[Release]`

**Context:** The upstream markdown looks like this (verified 2026-08-20, 38 KB, 71 releases):

```markdown
# Release 11.43.0 (2026-08-13)

## Updates

* Initial on-prem Signal and Managed-Agents support (GCP only) (#82102)

***

# Release 11.42.0 (2026-08-11)

## Upgrade Notes

* AWS storage defaults move from gp2 to gp3: ...

## Updates

* ...
```

Two details that bite: older entries carry a trailing ` (Maintenance)` after the date, and `***` horizontal rules separate entries and must be stripped from section bodies.

- [ ] **Step 1: Download the test fixture**

```bash
mkdir -p tests/fixtures
curl -sSL --fail "https://arize.com/docs/ax/selfhosting/on-premise-releases.md" \
  -o tests/fixtures/releases.md
grep -c '^# Release' tests/fixtures/releases.md
```

Expected: a number ≥ 71. The fixture is committed so tests never touch the network.

- [ ] **Step 2: Write the failing test**

Create `tests/test_releases.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from arize_upgrade.releases import (
    NoReleasesFound,
    Release,
    parse_releases,
    upgrade_notes_between,
)
from arize_upgrade.versions import Version

FIXTURE = (Path(__file__).parent / "fixtures" / "releases.md").read_text(encoding="utf-8")

SAMPLE = """\
# On-Premise Releases

> Release notes for self-hosted Arize AX distribution images.

# Release 11.43.0 (2026-08-13)

## Updates

* Something new (#82102)

***

# Release 11.42.0 (2026-08-11)

## Upgrade Notes

* Storage classes are immutable, pin them first.

## Updates

* Another change

***

# Release 11.41.0 (2026-07-31) (Maintenance)

## Updates

* Maintenance only
"""


def test_parses_every_release_in_the_sample():
    releases = parse_releases(SAMPLE)
    assert [str(r.version) for r in releases] == ["11.43.0", "11.42.0", "11.41.0"]


def test_parses_release_date():
    assert parse_releases(SAMPLE)[0].date == date(2026, 8, 13)


def test_tolerates_maintenance_suffix():
    oldest = parse_releases(SAMPLE)[-1]
    assert oldest.version == Version(11, 41, 0)


def test_captures_upgrade_notes_only_where_present():
    by_version = {str(r.version): r for r in parse_releases(SAMPLE)}
    assert by_version["11.43.0"].upgrade_notes is None
    assert "Storage classes are immutable" in by_version["11.42.0"].upgrade_notes


def test_upgrade_notes_do_not_bleed_into_updates():
    notes = {str(r.version): r for r in parse_releases(SAMPLE)}["11.42.0"].upgrade_notes
    assert "Another change" not in notes


def test_horizontal_rules_are_stripped():
    for release in parse_releases(SAMPLE):
        assert "***" not in (release.updates or "")


def test_ignores_the_page_title_heading():
    assert all(r.version is not None for r in parse_releases(SAMPLE))
    assert len(parse_releases(SAMPLE)) == 3


def test_results_are_newest_first():
    releases = parse_releases(SAMPLE)
    assert releases == sorted(releases, key=lambda r: r.version, reverse=True)


def test_empty_document_raises():
    with pytest.raises(NoReleasesFound):
        parse_releases("# Some Other Page\n\nNothing here.\n")


def test_real_fixture_parses():
    releases = parse_releases(FIXTURE)
    assert len(releases) >= 71
    assert releases[0].version >= Version(11, 43, 0)


def test_real_fixture_has_upgrade_notes_somewhere():
    assert any(r.upgrade_notes for r in parse_releases(FIXTURE))


def test_upgrade_notes_between_is_exclusive_of_current_inclusive_of_target():
    releases = parse_releases(SAMPLE)
    selected = upgrade_notes_between(
        releases, current=Version(11, 41, 0), target=Version(11, 43, 0)
    )
    assert [str(r.version) for r in selected] == ["11.42.0"]


def test_upgrade_notes_between_returns_oldest_first():
    releases = [
        Release(Version(11, 43, 0), date(2026, 8, 13), "c", None),
        Release(Version(11, 42, 0), date(2026, 8, 11), "b", None),
        Release(Version(11, 41, 0), date(2026, 7, 31), "a", None),
    ]
    selected = upgrade_notes_between(
        releases, current=Version(11, 40, 0), target=Version(11, 43, 0)
    )
    assert [r.upgrade_notes for r in selected] == ["a", "b", "c"]


def test_upgrade_notes_between_ignores_releases_above_target():
    releases = parse_releases(SAMPLE)
    selected = upgrade_notes_between(
        releases, current=Version(11, 41, 0), target=Version(11, 42, 0)
    )
    assert [str(r.version) for r in selected] == ["11.42.0"]


def test_fetch_releases_uses_injected_fetcher():
    from arize_upgrade.releases import fetch_releases

    calls = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return SAMPLE

    releases = fetch_releases(fetch=fake_fetch)
    assert len(releases) == 3
    assert calls == ["https://arize.com/docs/ax/selfhosting/on-premise-releases.md"]
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_releases.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.releases'`.

- [ ] **Step 4: Write the implementation**

Create `src/arize_upgrade/releases.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_releases.py -q
```

Expected: PASS, 15 passed.

- [ ] **Step 6: Commit**

```bash
git add src/arize_upgrade/releases.py tests/test_releases.py tests/fixtures/releases.md
git commit -m "feat: parse Arize release notes from the markdown endpoint"
```

---

### Task 3: Notification core types and provider factory

**Files:**
- Create: `src/arize_upgrade/notify/__init__.py`
- Create: `src/arize_upgrade/notify/base.py`
- Create: `src/arize_upgrade/notify/factory.py`
- Test: `tests/test_notify_factory.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Status = Literal["info", "success", "failure"]`
  - `Button` (frozen: `label: str`, `url: str`)
  - `Notification` (frozen: `title: str`, `fields: dict[str, str]`, `body: str | None`, `buttons: tuple[Button, ...]`, `status: Status`)
  - `Notifier` protocol with `send(notification: Notification, reply_to: str | None = None) -> str | None`
  - `UnknownProvider(ValueError)`, `MissingProviderConfig(ValueError)`
  - `build_notifier(env: Mapping[str, str]) -> Notifier`

Note `buttons` is a **tuple**, not a list, so `Notification` stays hashable and genuinely frozen. Tasks 4–6 must use tuples.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_factory.py`:

```python
import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.factory import (
    MissingProviderConfig,
    UnknownProvider,
    build_notifier,
)
from arize_upgrade.notify.slack import SlackNotifier
from arize_upgrade.notify.teams import TeamsNotifier


def test_builds_slack_notifier():
    notifier = build_notifier(
        {
            "NOTIFY_PROVIDER": "slack",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_CHANNEL_ID": "C123",
        }
    )
    assert isinstance(notifier, SlackNotifier)


def test_builds_teams_notifier():
    notifier = build_notifier(
        {
            "NOTIFY_PROVIDER": "teams",
            "TEAMS_WEBHOOK_URL": "https://example.com/hook",
        }
    )
    assert isinstance(notifier, TeamsNotifier)


def test_provider_is_case_insensitive():
    notifier = build_notifier(
        {"NOTIFY_PROVIDER": "SLACK", "SLACK_BOT_TOKEN": "x", "SLACK_CHANNEL_ID": "C1"}
    )
    assert isinstance(notifier, SlackNotifier)


def test_unknown_provider_raises_rather_than_silently_skipping():
    with pytest.raises(UnknownProvider):
        build_notifier({"NOTIFY_PROVIDER": "discord"})


def test_missing_provider_raises():
    with pytest.raises(UnknownProvider):
        build_notifier({})


def test_slack_without_token_raises():
    with pytest.raises(MissingProviderConfig):
        build_notifier({"NOTIFY_PROVIDER": "slack", "SLACK_CHANNEL_ID": "C1"})


def test_teams_without_webhook_raises():
    with pytest.raises(MissingProviderConfig):
        build_notifier({"NOTIFY_PROVIDER": "teams"})


def test_notification_is_frozen_and_hashable():
    notification = Notification(
        title="t",
        fields={},
        body=None,
        buttons=(Button("Open", "https://example.com"),),
        status="info",
    )
    assert hash(notification.buttons)
    with pytest.raises(Exception):
        notification.title = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_notify_factory.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.notify'`.

- [ ] **Step 3: Write the base types**

Create `src/arize_upgrade/notify/__init__.py` as an empty file. Create `src/arize_upgrade/notify/base.py`:

```python
"""Provider-agnostic notification types.

A Notification is built once from domain objects and rendered per provider.
Callers never branch on which provider is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Status = Literal["info", "success", "failure"]


@dataclass(frozen=True)
class Button:
    """A link button. Both Slack and Teams render these as real buttons."""

    label: str
    url: str


@dataclass(frozen=True)
class Notification:
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    buttons: tuple[Button, ...] = ()
    status: Status = "info"


class Notifier(Protocol):
    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        """Post a notification.

        Returns a thread reference if the provider supports threading,
        otherwise None. Callers must treat the return value as optional.
        """
        ...
```

- [ ] **Step 4: Write the factory**

Create `src/arize_upgrade/notify/factory.py`:

```python
"""Select exactly one notification provider from the environment."""

from __future__ import annotations

from typing import Mapping

from .base import Notifier


class UnknownProvider(ValueError):
    """Raised when NOTIFY_PROVIDER is unset or not recognised."""


class MissingProviderConfig(ValueError):
    """Raised when the selected provider's secrets are absent."""


def build_notifier(env: Mapping[str, str]) -> Notifier:
    provider = env.get("NOTIFY_PROVIDER", "").strip().lower()

    if provider == "slack":
        from .slack import SlackNotifier

        token = env.get("SLACK_BOT_TOKEN")
        channel = env.get("SLACK_CHANNEL_ID")
        if not token or not channel:
            raise MissingProviderConfig(
                "NOTIFY_PROVIDER=slack requires SLACK_BOT_TOKEN and SLACK_CHANNEL_ID"
            )
        return SlackNotifier(token=token, channel=channel)

    if provider == "teams":
        from .teams import TeamsNotifier

        webhook = env.get("TEAMS_WEBHOOK_URL")
        if not webhook:
            raise MissingProviderConfig(
                "NOTIFY_PROVIDER=teams requires TEAMS_WEBHOOK_URL"
            )
        return TeamsNotifier(webhook_url=webhook)

    raise UnknownProvider(
        f"NOTIFY_PROVIDER must be 'slack' or 'teams', got {provider!r}"
    )
```

- [ ] **Step 5: Run the test to confirm it now fails only on the missing providers**

```bash
.venv/bin/pytest tests/test_notify_factory.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.notify.slack'`. Tasks 4 and 5 supply those; this test file goes green at the end of Task 5. That is intentional: the factory's contract is what the providers are written against.

- [ ] **Step 6: Commit**

```bash
git add src/arize_upgrade/notify/__init__.py src/arize_upgrade/notify/base.py \
        src/arize_upgrade/notify/factory.py tests/test_notify_factory.py
git commit -m "feat: add provider-agnostic notification types and factory"
```

---

### Task 4: Slack notifier

**Files:**
- Create: `src/arize_upgrade/notify/slack.py`
- Test: `tests/test_notify_slack.py`

**Interfaces:**
- Consumes: `Notification`, `Button`, `Status` from Task 3.
- Produces: `render_blocks(notification: Notification) -> list[dict]` and `SlackNotifier(token: str, channel: str, *, post: Callable | None = None)` whose `send` returns the message `ts` so later messages thread under it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_slack.py`:

```python
import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.slack import SlackApiError, SlackNotifier, render_blocks

NOTIFICATION = Notification(
    title="Arize 11.43.0 available",
    fields={"Current": "11.41.0", "Target": "11.43.0"},
    body="* Storage classes are immutable.",
    buttons=(Button("Approve image push", "https://github.com/o/r/actions/runs/1"),),
    status="info",
)


def _blocks_of_type(blocks, kind):
    return [b for b in blocks if b["type"] == kind]


def test_title_is_rendered_as_a_header():
    header = _blocks_of_type(render_blocks(NOTIFICATION), "header")[0]
    assert "Arize 11.43.0 available" in header["text"]["text"]


def test_info_status_is_visible_in_the_header():
    info = Notification(title="Arize 11.43.0 available", fields={}, status="info")
    assert "\U0001f4e6" in str(render_blocks(info))


def test_fields_are_rendered():
    rendered = str(render_blocks(NOTIFICATION))
    assert "Current" in rendered and "11.41.0" in rendered


def test_body_is_rendered():
    assert "Storage classes are immutable" in str(render_blocks(NOTIFICATION))


def test_buttons_become_link_buttons_with_urls():
    actions = _blocks_of_type(render_blocks(NOTIFICATION), "actions")[0]
    element = actions["elements"][0]
    assert element["type"] == "button"
    assert element["url"] == "https://github.com/o/r/actions/runs/1"
    assert element["text"]["text"] == "Approve image push"


def test_notification_without_buttons_has_no_actions_block():
    plain = Notification(title="t", fields={}, body=None, buttons=(), status="info")
    assert _blocks_of_type(render_blocks(plain), "actions") == []


def test_failure_status_is_visible_in_the_header():
    failed = Notification(title="Upgrade failed", fields={}, status="failure")
    assert "❌" in str(render_blocks(failed))


def test_success_status_is_visible_in_the_header():
    ok = Notification(title="Upgrade complete", fields={}, status="success")
    assert "✅" in str(render_blocks(ok))


def test_send_posts_to_the_configured_channel():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers)
        return {"ok": True, "ts": "1700000000.000100"}

    notifier = SlackNotifier(token="xoxb-x", channel="C123", post=fake_post)
    notifier.send(NOTIFICATION)

    assert captured["url"] == "https://slack.com/api/chat.postMessage"
    assert captured["json"]["channel"] == "C123"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-x"


def test_send_returns_the_thread_reference():
    notifier = SlackNotifier(
        token="x", channel="C1", post=lambda **kw: {"ok": True, "ts": "111.222"}
    )
    assert notifier.send(NOTIFICATION) == "111.222"


def test_reply_to_threads_the_message():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "333.444"}

    notifier = SlackNotifier(token="x", channel="C1", post=fake_post)
    notifier.send(NOTIFICATION, reply_to="111.222")
    assert captured["json"]["thread_ts"] == "111.222"


def test_no_thread_ts_key_when_not_replying():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "1"}

    SlackNotifier(token="x", channel="C1", post=fake_post).send(NOTIFICATION)
    assert "thread_ts" not in captured["json"]


def test_slack_api_error_is_raised():
    notifier = SlackNotifier(
        token="x",
        channel="C1",
        post=lambda **kw: {"ok": False, "error": "channel_not_found"},
    )
    with pytest.raises(SlackApiError, match="channel_not_found"):
        notifier.send(NOTIFICATION)


def test_fallback_text_is_set_for_notifications():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "1"}

    SlackNotifier(token="x", channel="C1", post=fake_post).send(NOTIFICATION)
    assert captured["json"]["text"] == "Arize 11.43.0 available"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_notify_slack.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.notify.slack'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/notify/slack.py`:

```python
"""Slack notifier: Block Kit rendering over chat.postMessage."""

from __future__ import annotations

from typing import Any, Callable

from .base import Notification, Status

POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

_STATUS_ICON: dict[Status, str] = {
    "info": "\U0001f4e6",  # package
    "success": "✅",  # check mark
    "failure": "❌",  # cross mark
}


class SlackApiError(RuntimeError):
    """Raised when Slack responds with ok=false."""


def render_blocks(notification: Notification) -> list[dict[str, Any]]:
    icon = _STATUS_ICON[notification.status]
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{icon} {notification.title}"[:150],
                "emoji": True,
            },
        }
    ]

    if notification.fields:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{key}*\n{value}"}
                    for key, value in notification.fields.items()
                ],
            }
        )

    if notification.body:
        # Slack rejects text blocks over 3000 characters.
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": notification.body[:2900]},
            }
        )

    if notification.buttons:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": button.label,
                            "emoji": True,
                        },
                        "url": button.url,
                    }
                    for button in notification.buttons
                ],
            }
        )

    return blocks


def _default_post(url: str, json: dict, headers: dict, timeout: float) -> dict:
    import requests

    response = requests.post(url, json=json, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


class SlackNotifier:
    """Posts to Slack, threading every message under the first one."""

    def __init__(
        self,
        token: str,
        channel: str,
        *,
        post: Callable[..., dict] | None = None,
    ) -> None:
        self._token = token
        self._channel = channel
        self._post = post or _default_post

    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        payload: dict[str, Any] = {
            "channel": self._channel,
            # Fallback text for notifications and accessibility.
            "text": notification.title,
            "blocks": render_blocks(notification),
        }
        if reply_to:
            payload["thread_ts"] = reply_to

        body = self._post(
            url=POST_MESSAGE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=30,
        )
        if not body.get("ok"):
            raise SlackApiError(f"chat.postMessage failed: {body.get('error')}")
        return body.get("ts")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_notify_slack.py -q
```

Expected: PASS, 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arize_upgrade/notify/slack.py tests/test_notify_slack.py
git commit -m "feat: add Slack notifier with Block Kit rendering and threading"
```

---

### Task 5: Teams notifier

**Files:**
- Create: `src/arize_upgrade/notify/teams.py`
- Test: `tests/test_notify_teams.py`

**Interfaces:**
- Consumes: `Notification`, `Button`, `Status` from Task 3.
- Produces: `render_card(notification: Notification) -> dict` (an Adaptive Card 1.4 wrapped in the Teams attachment envelope) and `TeamsNotifier(webhook_url: str, *, post: Callable | None = None)` whose `send` always returns `None`.

**Context:** Microsoft retired Office 365 Connectors. The current path is a Power Automate "when a Teams webhook request is received" flow, which accepts an Adaptive Card payload. Webhooks cannot thread, so `send` returns `None` and each card must be self-contained — it restates the version and carries the run link.

- [ ] **Step 1: Write the failing test**

Create `tests/test_notify_teams.py`:

```python
import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.teams import TeamsNotifier, TeamsWebhookError, render_card

NOTIFICATION = Notification(
    title="Arize 11.43.0 available",
    fields={"Current": "11.41.0", "Target": "11.43.0"},
    body="* Storage classes are immutable.",
    buttons=(Button("Approve image push", "https://github.com/o/r/actions/runs/1"),),
    status="info",
)


def _card(notification=NOTIFICATION):
    return render_card(notification)["attachments"][0]["content"]


def test_payload_uses_the_adaptive_card_attachment_envelope():
    payload = render_card(NOTIFICATION)
    attachment = payload["attachments"][0]
    assert payload["type"] == "message"
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_card_declares_a_supported_schema_version():
    assert _card()["version"] == "1.4"


def test_title_is_the_first_text_block():
    first = _card()["body"][0]
    assert first["type"] == "TextBlock"
    assert "Arize 11.43.0 available" in first["text"]


def test_fields_render_as_a_factset():
    factsets = [b for b in _card()["body"] if b["type"] == "FactSet"]
    facts = {f["title"]: f["value"] for f in factsets[0]["facts"]}
    assert facts == {"Current": "11.41.0", "Target": "11.43.0"}


def test_body_is_rendered():
    assert "Storage classes are immutable" in str(_card()["body"])


def test_buttons_become_openurl_actions():
    action = _card()["actions"][0]
    assert action["type"] == "Action.OpenUrl"
    assert action["title"] == "Approve image push"
    assert action["url"] == "https://github.com/o/r/actions/runs/1"


def test_notification_without_buttons_has_no_actions():
    plain = Notification(title="t", fields={}, buttons=())
    assert render_card(plain)["attachments"][0]["content"].get("actions", []) == []


def test_failure_status_is_visible():
    failed = Notification(title="Upgrade failed", status="failure")
    assert "❌" in str(render_card(failed))


def test_success_status_is_visible():
    ok = Notification(title="Upgrade complete", status="success")
    assert "✅" in str(render_card(ok))


def test_send_posts_to_the_webhook_url():
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, json=json)
        return 202

    TeamsNotifier(webhook_url="https://example.com/hook", post=fake_post).send(
        NOTIFICATION
    )
    assert captured["url"] == "https://example.com/hook"
    assert captured["json"]["type"] == "message"


def test_send_returns_none_because_teams_cannot_thread():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 202
    )
    assert notifier.send(NOTIFICATION) is None


def test_reply_to_is_accepted_and_ignored():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 200
    )
    assert notifier.send(NOTIFICATION, reply_to="111.222") is None


def test_non_2xx_response_raises():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 500
    )
    with pytest.raises(TeamsWebhookError, match="500"):
        notifier.send(NOTIFICATION)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_notify_teams.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.notify.teams'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/notify/teams.py`:

```python
"""Microsoft Teams notifier: Adaptive Card over a Power Automate webhook.

Teams incoming webhooks cannot thread, so ``send`` returns None and every card
restates the version and carries the run link, making it readable alone.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import Notification, Status

_STATUS_ICON: dict[Status, str] = {
    "info": "\U0001f4e6",  # package
    "success": "✅",  # check mark
    "failure": "❌",  # cross mark
}


class TeamsWebhookError(RuntimeError):
    """Raised when the Teams webhook returns a non-2xx status."""


def render_card(notification: Notification) -> dict[str, Any]:
    icon = _STATUS_ICON[notification.status]
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{icon} {notification.title}",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        }
    ]

    if notification.fields:
        body.append(
            {
                "type": "FactSet",
                "facts": [
                    {"title": key, "value": value}
                    for key, value in notification.fields.items()
                ],
            }
        )

    if notification.body:
        body.append({"type": "TextBlock", "text": notification.body, "wrap": True})

    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [
            {"type": "Action.OpenUrl", "title": button.label, "url": button.url}
            for button in notification.buttons
        ],
    }

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def _default_post(url: str, json: dict, timeout: float) -> int:
    import requests

    return requests.post(url, json=json, timeout=timeout).status_code


class TeamsNotifier:
    def __init__(
        self,
        webhook_url: str,
        *,
        post: Callable[..., int] | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._post = post or _default_post

    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        # reply_to is accepted for interface compatibility and ignored:
        # Teams incoming webhooks have no threading model.
        status = self._post(
            url=self._webhook_url, json=render_card(notification), timeout=30
        )
        if not 200 <= status < 300:
            raise TeamsWebhookError(f"Teams webhook returned HTTP {status}")
        return None
```

- [ ] **Step 4: Run both notifier suites and the factory suite**

```bash
.venv/bin/pytest tests/test_notify_teams.py tests/test_notify_slack.py tests/test_notify_factory.py -q
```

Expected: PASS. The factory suite from Task 3 now goes green because both providers exist.

- [ ] **Step 5: Commit**

```bash
git add src/arize_upgrade/notify/teams.py tests/test_notify_teams.py
git commit -m "feat: add Teams notifier rendering Adaptive Cards"
```

---

### Task 6: Stage message composition

**Files:**
- Create: `src/arize_upgrade/messages.py`
- Test: `tests/test_messages.py`

**Interfaces:**
- Consumes: `Version` (Task 1), `Release` (Task 2), `Notification`/`Button` (Task 3).
- Produces four builders, each returning a `Notification`:
  - `detected(current: Version, target: Version, notes: list[Release], run_url: str) -> Notification`
  - `images_pushed(target: Version, registry: str, run_url: str) -> Notification`
  - `result(target: Version, succeeded: bool, app_url: str, run_url: str) -> Notification`
  - `alert(title: str, detail: str, run_url: str) -> Notification`

- [ ] **Step 1: Write the failing test**

Create `tests/test_messages.py`:

```python
from datetime import date

from arize_upgrade import messages
from arize_upgrade.releases import Release
from arize_upgrade.versions import Version

CURRENT = Version(11, 41, 0)
TARGET = Version(11, 43, 0)
RUN_URL = "https://github.com/o/r/actions/runs/42"
NOTES = [
    Release(Version(11, 42, 0), date(2026, 8, 11), "Pin your storage classes.", None)
]


def test_detected_names_both_versions_in_fields():
    notification = messages.detected(CURRENT, TARGET, NOTES, RUN_URL)
    assert notification.fields["Currently deployed"] == "11.41.0"
    assert notification.fields["New version"] == "11.43.0"


def test_detected_title_carries_the_target_version():
    assert "11.43.0" in messages.detected(CURRENT, TARGET, NOTES, RUN_URL).title


def test_detected_includes_upgrade_notes_with_their_version():
    body = messages.detected(CURRENT, TARGET, NOTES, RUN_URL).body
    assert "11.42.0" in body
    assert "Pin your storage classes." in body


def test_detected_says_so_when_there_are_no_upgrade_notes():
    body = messages.detected(CURRENT, TARGET, [], RUN_URL).body
    assert "No upgrade notes" in body


def test_detected_button_points_at_the_run():
    button = messages.detected(CURRENT, TARGET, NOTES, RUN_URL).buttons[0]
    assert button.url == RUN_URL
    assert "image" in button.label.lower()


def test_images_pushed_names_the_registry():
    notification = messages.images_pushed(TARGET, "123.dkr.ecr.eu-west-1.amazonaws.com", RUN_URL)
    assert "123.dkr.ecr.eu-west-1.amazonaws.com" in notification.fields.values()


def test_images_pushed_restates_the_version_for_unthreaded_providers():
    notification = messages.images_pushed(TARGET, "reg", RUN_URL)
    assert "11.43.0" in notification.title or "11.43.0" in str(notification.fields)


def test_images_pushed_button_asks_for_install_approval():
    button = messages.images_pushed(TARGET, "reg", RUN_URL).buttons[0]
    assert button.url == RUN_URL
    assert "install" in button.label.lower()


def test_successful_result_is_marked_success():
    notification = messages.result(TARGET, True, "https://arize.example.com", RUN_URL)
    assert notification.status == "success"


def test_successful_result_offers_a_link_to_the_app():
    buttons = messages.result(TARGET, True, "https://arize.example.com", RUN_URL).buttons
    assert any(b.url == "https://arize.example.com" for b in buttons)


def test_failed_result_is_marked_failure():
    notification = messages.result(TARGET, False, "https://arize.example.com", RUN_URL)
    assert notification.status == "failure"


def test_failed_result_links_the_run_logs_and_not_the_app():
    notification = messages.result(TARGET, False, "https://arize.example.com", RUN_URL)
    urls = [b.url for b in notification.buttons]
    assert RUN_URL in urls
    assert "https://arize.example.com" not in urls


def test_alert_is_a_failure_with_the_detail_in_the_body():
    notification = messages.alert("Parser broke", "no headings found", RUN_URL)
    assert notification.status == "failure"
    assert "no headings found" in notification.body
    assert notification.buttons[0].url == RUN_URL
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_messages.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.messages'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/messages.py`:

```python
"""Build the Notification for each stage of the upgrade.

Every message restates the target version so it reads correctly on providers
without threading (Teams).
"""

from __future__ import annotations

from .notify.base import Button, Notification
from .releases import Release
from .versions import Version


def _format_notes(notes: list[Release]) -> str:
    if not notes:
        return "_No upgrade notes between these versions._"
    sections = [f"*{release.version}*\n{release.upgrade_notes}" for release in notes]
    return "*Upgrade notes*\n\n" + "\n\n".join(sections)


def detected(
    current: Version, target: Version, notes: list[Release], run_url: str
) -> Notification:
    return Notification(
        title=f"Arize {target} is available",
        fields={
            "Currently deployed": str(current),
            "New version": str(target),
        },
        body=_format_notes(notes),
        buttons=(Button("Review and approve image push", run_url),),
        status="info",
    )


def images_pushed(target: Version, registry: str, run_url: str) -> Notification:
    return Notification(
        title=f"Arize {target} images are in ECR",
        fields={"Version": str(target), "Registry": registry},
        body="Images are pushed. Approve the install to upgrade the cluster.",
        buttons=(Button("Review and approve install", run_url),),
        status="info",
    )


def result(
    target: Version, succeeded: bool, app_url: str, run_url: str
) -> Notification:
    if succeeded:
        return Notification(
            title=f"Arize upgraded to {target}",
            fields={"Version": str(target), "Status": "Healthy"},
            body="All init jobs completed and every workload reported ready.",
            buttons=(
                Button("Open Arize", app_url),
                Button("View run", run_url),
            ),
            status="success",
        )
    return Notification(
        title=f"Arize upgrade to {target} FAILED",
        fields={"Version": str(target), "Status": "Failed"},
        body=(
            "The cluster may be partially upgraded. There is no automatic "
            "rollback. Check the run logs before retrying."
        ),
        buttons=(Button("View run logs", run_url),),
        status="failure",
    )


def alert(title: str, detail: str, run_url: str) -> Notification:
    return Notification(
        title=title,
        fields={},
        body=detail,
        buttons=(Button("View run logs", run_url),),
        status="failure",
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_messages.py -q
```

Expected: PASS, 13 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arize_upgrade/messages.py tests/test_messages.py
git commit -m "feat: compose the four upgrade stage notifications"
```

---

### Task 7: Deployment state via GitHub Releases

**Files:**
- Create: `src/arize_upgrade/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `Version` from Task 1.
- Produces:
  - `TAG_PREFIX = "deployed/"`
  - `DeployedVersionUnknown(RuntimeError)`
  - `read_deployed_version(env: Mapping[str, str], *, run=None) -> Version`
  - `record_deployment(version: Version, *, notes: str, run=None) -> None`
  - `upgrade_in_progress(*, run=None) -> bool`

The injected `run` matches `subprocess.run(argv, capture_output=True, text=True, check=False)` and returns an object with `.returncode` and `.stdout`.

**Context:** A run paused at an environment approval gate has GitHub status **`waiting`**, not `in_progress`. `upgrade_in_progress` must count `queued`, `in_progress`, and `waiting`, or the daily cron will dispatch a second upgrade while the first is still awaiting a human.

- [ ] **Step 1: Write the failing test**

Create `tests/test_state.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_state.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.state'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/state.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_state.py -q
```

Expected: PASS, 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arize_upgrade/state.py tests/test_state.py
git commit -m "feat: track deployed version via GitHub Releases"
```

---

### Task 8: Distribution bundle verification

**Files:**
- Create: `src/arize_upgrade/bundle.py`
- Test: `tests/test_bundle.py`

**Interfaces:**
- Consumes: `Version` from Task 1.
- Produces:
  - `BUNDLE_DIR_PATTERN`
  - `BundleNotFound(RuntimeError)`, `BundleVersionMismatch(RuntimeError)`
  - `find_bundle_dir(root: Path) -> Path`
  - `bundle_version(path: Path) -> Version`
  - `verify_bundle(root: Path, expected: Version) -> Path`

**Context:** `get_latest.sh` serves *latest only* — there is no version-pinned download. It extracts into `arize-distribution-X.Y.Z/`. If a release lands between detection and this job, the downloaded bundle will not be what a human approved, so a mismatch must abort the run.

- [ ] **Step 1: Write the failing test**

Create `tests/test_bundle.py`:

```python
import pytest

from arize_upgrade.bundle import (
    BundleNotFound,
    BundleVersionMismatch,
    bundle_version,
    find_bundle_dir,
    verify_bundle,
)
from arize_upgrade.versions import Version


def make_bundle(root, name):
    path = root / name
    (path / "examples").mkdir(parents=True)
    (path / "arize.sh").write_text("#!/bin/bash\n")
    return path


def test_finds_the_bundle_directory(tmp_path):
    made = make_bundle(tmp_path, "arize-distribution-11.43.0")
    assert find_bundle_dir(tmp_path) == made


def test_ignores_unrelated_directories(tmp_path):
    (tmp_path / "notes").mkdir()
    made = make_bundle(tmp_path, "arize-distribution-11.43.0")
    assert find_bundle_dir(tmp_path) == made


def test_missing_bundle_raises(tmp_path):
    with pytest.raises(BundleNotFound):
        find_bundle_dir(tmp_path)


def test_two_bundles_raise_rather_than_picking_one(tmp_path):
    make_bundle(tmp_path, "arize-distribution-11.42.0")
    make_bundle(tmp_path, "arize-distribution-11.43.0")
    with pytest.raises(BundleNotFound, match="more than one"):
        find_bundle_dir(tmp_path)


def test_directory_without_arize_sh_is_not_a_bundle(tmp_path):
    (tmp_path / "arize-distribution-11.43.0").mkdir()
    with pytest.raises(BundleNotFound):
        find_bundle_dir(tmp_path)


def test_reads_the_version_from_the_directory_name(tmp_path):
    made = make_bundle(tmp_path, "arize-distribution-11.43.0")
    assert bundle_version(made) == Version(11, 43, 0)


def test_verify_returns_the_path_on_a_match(tmp_path):
    made = make_bundle(tmp_path, "arize-distribution-11.43.0")
    assert verify_bundle(tmp_path, Version(11, 43, 0)) == made


def test_verify_raises_when_a_newer_release_landed_mid_run(tmp_path):
    make_bundle(tmp_path, "arize-distribution-11.44.0")
    with pytest.raises(BundleVersionMismatch, match="11.43.0"):
        verify_bundle(tmp_path, Version(11, 43, 0))


def test_mismatch_message_names_both_versions(tmp_path):
    make_bundle(tmp_path, "arize-distribution-11.44.0")
    with pytest.raises(BundleVersionMismatch) as excinfo:
        verify_bundle(tmp_path, Version(11, 43, 0))
    assert "11.44.0" in str(excinfo.value)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_bundle.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.bundle'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/bundle.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/bin/pytest tests/test_bundle.py -q
```

Expected: PASS, 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arize_upgrade/bundle.py tests/test_bundle.py
git commit -m "feat: verify the downloaded bundle matches the approved version"
```

---

### Task 9: CLI

**Files:**
- Create: `src/arize_upgrade/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: `main(argv: list[str] | None = None) -> int` plus the console script `arize-upgrade` with subcommands `check`, `notify`, `verify-bundle`, and `record`.

**Context:** `check` writes `target_version` to `$GITHUB_OUTPUT` (empty when there is nothing to do) so the workflow can branch on it. Exit codes are the contract: `0` = nothing to do or success, `1` = hard failure the workflow must surface.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_cli.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'arize_upgrade.cli'`.

- [ ] **Step 3: Write the implementation**

Create `src/arize_upgrade/cli.py`:

```python
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
    import requests

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


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
```

- [ ] **Step 4: Run the whole suite**

```bash
.venv/bin/pytest -q
```

Expected: PASS, all tests green.

- [ ] **Step 5: Verify the console script is wired**

```bash
.venv/bin/arize-upgrade --help
```

Expected: usage text listing `check`, `notify`, `verify-bundle`, `record`.

- [ ] **Step 6: Commit**

```bash
git add src/arize_upgrade/cli.py tests/test_cli.py
git commit -m "feat: add the arize-upgrade CLI used by the workflows"
```

---

### Task 10: Values template and render script

**Files:**
- Create: `config/values.template.yaml` (generated)
- Create: `scripts/make-values-template.py`
- Create: `scripts/render-values.sh`
- Test: `tests/test_render_values.sh`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `config/values.template.yaml` and `scripts/render-values.sh <output-path>`, which renders the template using these ten environment variables: `ARIZE_HUB_JWT`, `ARIZE_CIPHER_KEY`, `ARIZE_POSTGRES_PASSWORD`, `ARIZE_SMTP_USER`, `ARIZE_SMTP_PASSWORD`, `ARIZE_GCP_SA_KEY`, `ARIZE_INTERNAL_TLS_CERT`, `ARIZE_INTERNAL_TLS_KEY`, `ARIZE_FLIGHT_TLS_CERT`, `ARIZE_FLIGHT_TLS_KEY`.

**Context:** The live `values.yaml` contains a GCP service-account private key, two TLS private keys, the Postgres password, SMTP credentials, and the Arize hub JWT. The template is generated *from* the real file by a script so no human retypes secrets and none are pasted into this plan.

- [ ] **Step 1: Write the template generator**

Create `scripts/make-values-template.py`:

```python
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

    lines = []
    for line in source.splitlines():
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

    output = Path("config/values.template.yaml")
    output.parent.mkdir(exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    missing = set(SECRET_FIELDS) - replaced
    print(f"wrote {output} ({len(replaced)} secrets templated)")
    if missing:
        print(f"note: not present in source, no placeholder added: {sorted(missing)}")

    leaked = [k for k in SECRET_FIELDS if f'{k}: "${{' not in rendered]
    if leaked and not missing:
        print(f"ERROR: these keys were not templated: {leaked}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Generate the template from the real values file**

```bash
python3 scripts/make-values-template.py \
  /Users/sean/projects/arize/arize-distribution-11.41.0/values.yaml
```

Expected: `wrote config/values.template.yaml (10 secrets templated)`.

- [ ] **Step 3: Verify no secrets leaked into the template**

```bash
grep -nE '^(hubJwt|cipherKey|postgresPassword|smtpUser|smtpPassword|multiCloudGcpServiceAccountKey|internalEndpointsAppTlsCert|internalEndpointsAppTlsKey|flightTlsCert|flightTlsKey):' \
  config/values.template.yaml
grep -c 'BEGIN PRIVATE KEY' config/values.template.yaml || true
```

Expected: every listed key shows `"${VAR}"` as its value, and the `BEGIN PRIVATE KEY` count is `0`. **If any real value remains, stop and fix the generator before committing.**

- [ ] **Step 4: Write the render script**

Create `scripts/render-values.sh`:

```bash
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
```

- [ ] **Step 5: Write the render test**

Create `tests/test_render_values.sh`:

```bash
#!/usr/bin/env bash
# Verifies rendering substitutes every placeholder and fails closed.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

export ARIZE_HUB_JWT=jwt ARIZE_CIPHER_KEY=cipher ARIZE_POSTGRES_PASSWORD=pg \
       ARIZE_SMTP_USER=smtpu ARIZE_SMTP_PASSWORD=smtpp ARIZE_GCP_SA_KEY=gcp \
       ARIZE_INTERNAL_TLS_CERT=ic ARIZE_INTERNAL_TLS_KEY=ik \
       ARIZE_FLIGHT_TLS_CERT=fc ARIZE_FLIGHT_TLS_KEY=fk

scripts/render-values.sh "$tmp/values.yaml"

grep -q 'hubJwt: "jwt"' "$tmp/values.yaml" || { echo "FAIL: hubJwt not substituted"; exit 1; }
grep -q 'pushRegistry:' "$tmp/values.yaml" || { echo "FAIL: pushRegistry missing"; exit 1; }
! grep -q '\${ARIZE_' "$tmp/values.yaml" || { echo "FAIL: placeholders remain"; exit 1; }

# Fails closed when a secret is absent.
( unset ARIZE_HUB_JWT; scripts/render-values.sh "$tmp/other.yaml" ) 2>/dev/null \
  && { echo "FAIL: missing secret did not fail"; exit 1; }

echo "PASS: render-values.sh"
```

- [ ] **Step 6: Run the render test**

```bash
chmod +x scripts/render-values.sh tests/test_render_values.sh
./tests/test_render_values.sh
```

Expected: `✅ rendered N lines ...` then `PASS: render-values.sh`.

- [ ] **Step 7: Commit**

```bash
git add config/values.template.yaml scripts/make-values-template.py \
        scripts/render-values.sh tests/test_render_values.sh
git commit -m "feat: template values.yaml with secrets injected at run time"
```

---

### Task 11: Runner disk preparation

**Files:**
- Create: `scripts/prepare-runner-disk.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `scripts/prepare-runner-disk.sh`, run once before `pull-images`.

**Context:** `the pull step()` (arize.sh line 645) pulls 26 images into the local Docker daemon and `the push step()` re-tags and pushes from there. `ubuntu-latest` has roughly 14 GB free on `/` but a much larger ephemeral volume at `/mnt`. Without this step the pull will exhaust the disk.

- [ ] **Step 1: Write the script**

Create `scripts/prepare-runner-disk.sh`:

```bash
#!/usr/bin/env bash
# Move Docker's storage to the runner's large ephemeral volume.
#
# arize.sh pull-images stages 26 images through the local Docker daemon.
# ubuntu-latest has ~14 GB free on / but ~65 GB on /mnt.
set -euo pipefail

echo "▶ Disk before:"
df -h / /mnt

sudo systemctl stop docker.socket docker || sudo systemctl stop docker

sudo mkdir -p /mnt/docker
printf '{\n  "data-root": "/mnt/docker"\n}\n' | sudo tee /etc/docker/daemon.json

sudo systemctl start docker
sudo systemctl is-active --quiet docker

root_dir="$(docker info --format '{{.DockerRootDir}}')"
echo "▶ Docker root: ${root_dir}"
if [ "${root_dir}" != "/mnt/docker" ]; then
  echo "🛑 Docker did not adopt /mnt/docker; aborting before the image pull" >&2
  exit 1
fi

echo "▶ Disk after:"
df -h /mnt
```

- [ ] **Step 2: Check the script parses and passes shellcheck**

```bash
chmod +x scripts/prepare-runner-disk.sh
bash -n scripts/prepare-runner-disk.sh && echo "syntax OK"
command -v shellcheck >/dev/null && shellcheck scripts/prepare-runner-disk.sh || echo "shellcheck not installed, skipped"
```

Expected: `syntax OK`, and no shellcheck errors if installed. The script itself can only be exercised on a real Linux runner — Task 13's first live run is its test.

- [ ] **Step 3: Commit**

```bash
git add scripts/prepare-runner-disk.sh
git commit -m "feat: relocate Docker storage to /mnt before pulling images"
```

---

### Task 12: Release check workflow

**Files:**
- Create: `.github/workflows/check-release.yml`

**Interfaces:**
- Consumes: the `arize-upgrade check` CLI from Task 9.
- Produces: a daily workflow that dispatches `upgrade.yml` with `target_version`.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/check-release.yml`:

```yaml
name: Check for Arize release

on:
  schedule:
    # 09:00 UTC, weekdays.
    - cron: "0 9 * * 1-5"
  workflow_dispatch:

permissions:
  contents: read
  actions: write

concurrency:
  group: arize-check-release
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install package
        run: pip install --quiet -e .

      - name: Check for a newer release
        id: check
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          DEPLOYED_VERSION: ${{ vars.DEPLOYED_VERSION }}
          NOTIFY_PROVIDER: ${{ vars.NOTIFY_PROVIDER }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_CHANNEL_ID: ${{ vars.SLACK_CHANNEL_ID }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}
        run: arize-upgrade check

      - name: Dispatch the upgrade
        if: steps.check.outputs.target_version != ''
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TARGET: ${{ steps.check.outputs.target_version }}
        run: |
          set -euo pipefail
          echo "Dispatching upgrade to ${TARGET}"
          gh workflow run upgrade.yml -f "target_version=${TARGET}"
```

- [ ] **Step 2: Validate the workflow with actionlint**

```bash
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color
```

Expected: no output (clean). If Docker is unavailable, install actionlint and run `actionlint`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/check-release.yml
git commit -m "feat: add daily release check workflow"
```

---

### Task 13: Upgrade workflow

**Files:**
- Create: `.github/workflows/upgrade.yml`

**Interfaces:**
- Consumes: the CLI (Task 9), `scripts/render-values.sh` (Task 10), `scripts/prepare-runner-disk.sh` (Task 11).
- Produces: the gated five-job pipeline.

**Context:** The two `environment:` declarations are the approval gates — a job declaring an environment with required reviewers pauses before its first step. `install` must alias the kubeconfig entry to the full EKS cluster ARN, because `arize.sh` sets `the cluster arguments` and `clusterName` is that ARN.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/upgrade.yml`:

```yaml
name: Upgrade Arize

on:
  workflow_dispatch:
    inputs:
      target_version:
        description: "Version to upgrade to, for example 11.43.0"
        required: true
        type: string

permissions:
  contents: write
  actions: read
  issues: write

concurrency:
  group: arize-upgrade
  cancel-in-progress: false

env:
  RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
  NOTIFY_PROVIDER: ${{ vars.NOTIFY_PROVIDER }}
  SLACK_CHANNEL_ID: ${{ vars.SLACK_CHANNEL_ID }}
  PUSH_REGISTRY: ${{ vars.PUSH_REGISTRY }}
  APP_BASE_URL: ${{ vars.APP_BASE_URL }}
  AWS_REGION: ${{ vars.AWS_REGION }}
  EKS_CLUSTER_NAME: ${{ vars.EKS_CLUSTER_NAME }}
  EKS_CLUSTER_ARN: ${{ vars.EKS_CLUSTER_ARN }}

jobs:
  announce:
    name: Announce the release
    runs-on: ubuntu-latest
    outputs:
      thread_ref: ${{ steps.notify.outputs.thread_ref }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e .
      - name: Post the approval request
        id: notify
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          DEPLOYED_VERSION: ${{ vars.DEPLOYED_VERSION }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}
        run: |
          arize-upgrade notify \
            --stage detected \
            --target "${{ inputs.target_version }}"

  push-images:
    name: Pull and push images to ECR
    needs: announce
    runs-on: ubuntu-latest
    environment: image-push
    timeout-minutes: 180
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e .

      - name: Prepare runner disk
        run: ./scripts/prepare-runner-disk.sh

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ vars.AWS_REGION }}

      - name: Log in to ECR
        run: |
          set -euo pipefail
          aws ecr get-login-password --region "${AWS_REGION}" \
            | docker login --username AWS --password-stdin "${PUSH_REGISTRY}"

      - name: Download the distribution
        env:
          JWT: ${{ secrets.ARIZE_HUB_JWT_RAW }}
        run: |
          set -euo pipefail
          mkdir -p dist && cd dist
          curl -sSf -H "Authorization: Bearer ${JWT}" \
            "https://ch.hub.arize.com/dist/get_latest.sh" | sh -

      - name: Verify the bundle is the approved version
        id: bundle
        run: |
          arize-upgrade verify-bundle \
            --dir dist \
            --expect "${{ inputs.target_version }}"

      - name: Render values.yaml
        env:
          ARIZE_HUB_JWT: ${{ secrets.ARIZE_HUB_JWT }}
          ARIZE_CIPHER_KEY: ${{ secrets.ARIZE_CIPHER_KEY }}
          ARIZE_POSTGRES_PASSWORD: ${{ secrets.ARIZE_POSTGRES_PASSWORD }}
          ARIZE_SMTP_USER: ${{ secrets.ARIZE_SMTP_USER }}
          ARIZE_SMTP_PASSWORD: ${{ secrets.ARIZE_SMTP_PASSWORD }}
          ARIZE_GCP_SA_KEY: ${{ secrets.ARIZE_GCP_SA_KEY }}
          ARIZE_INTERNAL_TLS_CERT: ${{ secrets.ARIZE_INTERNAL_TLS_CERT }}
          ARIZE_INTERNAL_TLS_KEY: ${{ secrets.ARIZE_INTERNAL_TLS_KEY }}
          ARIZE_FLIGHT_TLS_CERT: ${{ secrets.ARIZE_FLIGHT_TLS_CERT }}
          ARIZE_FLIGHT_TLS_KEY: ${{ secrets.ARIZE_FLIGHT_TLS_KEY }}
        run: ./scripts/render-values.sh "${{ steps.bundle.outputs.bundle_dir }}/values.yaml"

      - name: Pull images from the Arize registry
        working-directory: ${{ steps.bundle.outputs.bundle_dir }}
        run: ./arize.sh -y -q pull-images

      - name: Push images to ECR
        working-directory: ${{ steps.bundle.outputs.bundle_dir }}
        run: ./arize.sh -y -q push-images

      - name: Clean up
        if: always()
        run: |
          set -euo pipefail
          rm -f dist/*/values.yaml
          docker image prune -af || true
          df -h /mnt

  announce-images:
    name: Request install approval
    needs: [announce, push-images]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e .
      - name: Post the second approval request
        env:
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}
        run: |
          arize-upgrade notify \
            --stage images \
            --target "${{ inputs.target_version }}" \
            --reply-to "${{ needs.announce.outputs.thread_ref }}"

  install:
    name: Install on the cluster
    needs: [announce, announce-images]
    runs-on: ubuntu-latest
    environment: cluster-install
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e .

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ vars.AWS_REGION }}

      - uses: azure/setup-helm@v4
        with:
          version: v3.15.4

      - name: Point kubectl at the cluster
        run: |
          set -euo pipefail
          # arize.sh runs `kubectl --cluster=$clusterName`, and clusterName is
          # the full EKS ARN, so the kubeconfig entry must use that exact alias.
          aws eks update-kubeconfig \
            --region "${AWS_REGION}" \
            --name "${EKS_CLUSTER_NAME}" \
            --alias "${EKS_CLUSTER_ARN}"
          kubectl config get-contexts

      - name: Download the distribution
        env:
          JWT: ${{ secrets.ARIZE_HUB_JWT_RAW }}
        run: |
          set -euo pipefail
          mkdir -p dist && cd dist
          curl -sSf -H "Authorization: Bearer ${JWT}" \
            "https://ch.hub.arize.com/dist/get_latest.sh" | sh -

      - name: Verify the bundle is the approved version
        id: bundle
        run: |
          arize-upgrade verify-bundle \
            --dir dist \
            --expect "${{ inputs.target_version }}"

      - name: Render values.yaml
        env:
          ARIZE_HUB_JWT: ${{ secrets.ARIZE_HUB_JWT }}
          ARIZE_CIPHER_KEY: ${{ secrets.ARIZE_CIPHER_KEY }}
          ARIZE_POSTGRES_PASSWORD: ${{ secrets.ARIZE_POSTGRES_PASSWORD }}
          ARIZE_SMTP_USER: ${{ secrets.ARIZE_SMTP_USER }}
          ARIZE_SMTP_PASSWORD: ${{ secrets.ARIZE_SMTP_PASSWORD }}
          ARIZE_GCP_SA_KEY: ${{ secrets.ARIZE_GCP_SA_KEY }}
          ARIZE_INTERNAL_TLS_CERT: ${{ secrets.ARIZE_INTERNAL_TLS_CERT }}
          ARIZE_INTERNAL_TLS_KEY: ${{ secrets.ARIZE_INTERNAL_TLS_KEY }}
          ARIZE_FLIGHT_TLS_CERT: ${{ secrets.ARIZE_FLIGHT_TLS_CERT }}
          ARIZE_FLIGHT_TLS_KEY: ${{ secrets.ARIZE_FLIGHT_TLS_KEY }}
        run: ./scripts/render-values.sh "${{ steps.bundle.outputs.bundle_dir }}/values.yaml"

      - name: Install
        working-directory: ${{ steps.bundle.outputs.bundle_dir }}
        run: ./arize.sh -y -q -t 3600 install

      - name: Wait for the cluster to report healthy
        working-directory: ${{ steps.bundle.outputs.bundle_dir }}
        run: ./arize.sh -y -q install-status

      - name: Clean up
        if: always()
        run: rm -f dist/*/values.yaml

  record:
    name: Report the outcome
    needs: [announce, push-images, install]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e .

      - name: Determine the outcome
        id: outcome
        run: |
          set -euo pipefail
          if [ "${{ needs.install.result }}" = "success" ]; then
            echo "value=success" >> "$GITHUB_OUTPUT"
          else
            echo "value=failure" >> "$GITHUB_OUTPUT"
          fi

      - name: Post the result
        env:
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          TEAMS_WEBHOOK_URL: ${{ secrets.TEAMS_WEBHOOK_URL }}
        run: |
          arize-upgrade notify \
            --stage result \
            --target "${{ inputs.target_version }}" \
            --outcome "${{ steps.outcome.outputs.value }}" \
            --reply-to "${{ needs.announce.outputs.thread_ref }}"

      - name: Record the deployment
        if: steps.outcome.outputs.value == 'success'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          arize-upgrade record --version "${{ inputs.target_version }}"

      - name: Open a failure issue
        if: steps.outcome.outputs.value == 'failure'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          TARGET: ${{ inputs.target_version }}
        run: |
          set -euo pipefail
          gh issue create \
            --title "Arize upgrade to ${TARGET} failed" \
            --label "arize-upgrade" \
            --body "$(cat <<EOF
          The upgrade to \`${TARGET}\` did not complete.

          - Run: ${RUN_URL}
          - Image push: ${{ needs['push-images'].result }}
          - Install: ${{ needs.install.result }}

          There is no automatic rollback. The cluster may be partially upgraded.
          Review the run logs before retrying.
          EOF
          )"
```

- [ ] **Step 2: Validate with actionlint**

```bash
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color
```

Expected: no output.

- [ ] **Step 3: Confirm the approval gates and job graph are correct**

```bash
python3 - <<'PY'
import re
text = open(".github/workflows/upgrade.yml").read()
assert "environment: image-push" in text, "missing first approval gate"
assert "environment: cluster-install" in text, "missing second approval gate"

invocations = re.findall(r"\./arize\.sh[^\n]*", text)
assert len(invocations) >= 4, f"expected >=4 arize.sh calls, found {len(invocations)}"
for call in invocations:
    assert " -y " in call, f"missing -y (non-interactive): {call}"
    assert " -q " in call, f"missing -q (no banner): {call}"
    # -v would echo rendered values.yaml contents into the run log.
    assert not re.search(r"(?<![-\w])-v(?![-\w])", call), f"verbose flag leaks secrets: {call}"

assert "cancel-in-progress: false" in text
assert "issues: write" in text, "record job needs issues: write to open a failure issue"
print(f"workflow structure OK ({len(invocations)} arize.sh calls checked)")
PY
```

Expected: `workflow structure OK`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/upgrade.yml
git commit -m "feat: add gated upgrade workflow"
```

---

### Task 14: CI, README, and setup documentation

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: everything.
- Produces: a CI workflow running pytest, actionlint, and the render test on every push and PR, plus operator-facing setup docs.

- [ ] **Step 1: Write the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install --quiet -e ".[dev]"
      - run: pytest -q
      - run: ./tests/test_render_values.sh
      - name: Lint workflows
        uses: raven-actions/actionlint@v2
      - name: Lint shell scripts
        run: |
          sudo apt-get update -qq && sudo apt-get install -y -qq shellcheck
          shellcheck scripts/*.sh tests/*.sh
```

- [ ] **Step 2: Write the README**

Create `README.md`:

````markdown
# Arize Auto-Upgrade

Automated upgrade pipeline for a self-hosted Arize AX cluster on EKS, with two
human approval gates in Slack or Microsoft Teams.

## How it works

1. **Daily at 09:00 UTC**, `check-release.yml` parses
   <https://arize.com/docs/ax/selfhosting/on-premise-releases.md> and compares
   the newest release against the deployed version.
2. If a newer release exists it dispatches `upgrade.yml`, which posts the
   release and its upgrade notes to chat with an **Approve image push** button.
3. After approval, images are pulled from `ch.hub.arize.com` and pushed to ECR.
4. Chat gets a second message with an **Approve install** button.
5. After approval, `./arize.sh install` runs, gated on `install-status`.
6. Chat gets the result with an **Open Arize** button, and a GitHub Release
   tagged `deployed/<version>` records the new state.

Approvals use GitHub Environments, so every button is a link into the run's
approval page. That is why Slack and Teams are interchangeable.

## Setup

### 1. Repository variables

| Variable | Example | Purpose |
|---|---|---|
| `NOTIFY_PROVIDER` | `slack` | `slack` or `teams`. Exactly one. |
| `SLACK_CHANNEL_ID` | `C0123456789` | Slack only. |
| `PUSH_REGISTRY` | `123456789012.dkr.ecr.ap-northeast-2.amazonaws.com` | ECR registry host. |
| `APP_BASE_URL` | `https://arize-app.example.com` | Linked from the result message. |
| `AWS_REGION` | `ap-northeast-2` | |
| `EKS_CLUSTER_NAME` | `my-cluster` | Short name for `update-kubeconfig`. |
| `EKS_CLUSTER_ARN` | `arn:aws:eks:ap-northeast-2:123456789012:cluster/my-cluster` | Must equal `clusterName` in values. |
| `DEPLOYED_VERSION` | `11.41.0` | Bootstrap only; ignored once a `deployed/*` Release exists. |

```bash
gh variable set NOTIFY_PROVIDER --body slack
gh variable set DEPLOYED_VERSION --body 11.41.0
```

### 2. Secrets

Set on **both** the `image-push` and `cluster-install` environments:

| Secret | Notes |
|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Needs ECR push, `ecr:CreateRepository`, and EKS access. |
| `ARIZE_HUB_JWT_RAW` | The JWT as issued by Arize, for the distribution download. |
| `ARIZE_HUB_JWT` | The base64 form that goes into `values.yaml`. |
| `ARIZE_CIPHER_KEY`, `ARIZE_POSTGRES_PASSWORD` | |
| `ARIZE_SMTP_USER`, `ARIZE_SMTP_PASSWORD` | |
| `ARIZE_GCP_SA_KEY` | |
| `ARIZE_INTERNAL_TLS_CERT`, `ARIZE_INTERNAL_TLS_KEY` | |
| `ARIZE_FLIGHT_TLS_CERT`, `ARIZE_FLIGHT_TLS_KEY` | |

`ARIZE_HUB_JWT_RAW` and `ARIZE_HUB_JWT` are different encodings of the same
credential. `arize.sh` does `license=$(echo -n $hubJwt | base64 -d)`, so the
value in `values.yaml` is base64-encoded, while `get_latest.sh` wants the raw
JWT in an `Authorization: Bearer` header.

Repository-level secrets are also needed for `check-release.yml`:
`SLACK_BOT_TOKEN` or `TEAMS_WEBHOOK_URL`.

### 3. Environments

Create two environments, each with **required reviewers**:

- `image-push` — gates pulling and pushing images
- `cluster-install` — gates touching the cluster

Without reviewers configured, the jobs run unattended and there are no approvals.

### 4. Chat

**Slack:** create an app with the `chat:write` bot scope, install it to the
workspace, invite it to the channel, and set `SLACK_BOT_TOKEN` (`xoxb-…`) and
`SLACK_CHANNEL_ID`.

**Teams:** in the target channel add a **Workflows** app flow from the
"post to a channel when a webhook request is received" template, then set
`TEAMS_WEBHOOK_URL`. Teams webhooks cannot thread, so each stage arrives as its
own card.

### 5. Values template

`config/values.template.yaml` is generated from a real `values.yaml`:

```bash
python3 scripts/make-values-template.py /path/to/values.yaml
grep -c 'BEGIN PRIVATE KEY' config/values.template.yaml   # must be 0
```

`values.yaml` is gitignored and must never be committed.

## Prerequisites this repo cannot solve

- The EKS API endpoint must be reachable from GitHub-hosted runners.
- The IAM principal must be mapped in EKS access entries with install rights.
- A valid Arize hub JWT.

## Operational notes

- **No rollback.** Upgrades run irreversible Postgres, Druid, and gazette init
  jobs. A failure notifies and stops; recovery uses `arize.sh backup-db-local`
  and `restore-from-*`.
- **Jump to latest.** `get_latest.sh` serves only the newest release, so
  intermediate versions cannot be pinned. All intervening upgrade notes are
  surfaced at approval time instead.
- **Disk.** `pull-images` stages 26 images through the Docker daemon.
  `scripts/prepare-runner-disk.sh` moves Docker to `/mnt`. If a future release
  still overflows, switch to `./arize.sh -y -q --skopeo load-remote-images`,
  which copies registry-to-registry and uses no local disk.
- **Approvals expire.** GitHub cancels a run awaiting approval after 30 days;
  the next scheduled check re-detects and re-dispatches.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
./tests/test_render_values.sh
```
````

- [ ] **Step 3: Run the full verification suite**

```bash
.venv/bin/pytest -q
./tests/test_render_values.sh
docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color && echo "actionlint clean"
```

Expected: all tests pass, render test passes, actionlint clean.

- [ ] **Step 4: Confirm no secrets are tracked**

```bash
git ls-files | grep -E 'values\.yaml$' && echo "FAIL: values.yaml is tracked" || echo "OK: values.yaml untracked"
git grep -l 'BEGIN PRIVATE KEY' -- . && echo "FAIL: private key committed" || echo "OK: no private keys"
```

Expected: `OK: values.yaml untracked` and `OK: no private keys`.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "docs: add CI workflow and operator setup guide"
```

---

## Post-implementation checklist

Work through this with the operator; none of it can be done from the repo alone.

- [ ] Seed `DEPLOYED_VERSION` with the version currently on the cluster.
- [ ] Create the `image-push` and `cluster-install` environments **with required reviewers**.
- [ ] Add all secrets to both environments.
- [ ] **Rotate the credentials that were in the working `values.yaml`** — GCP service-account key, both TLS key pairs, Postgres password, SMTP credentials, and the hub JWT.
- [ ] Confirm the EKS API endpoint is reachable from GitHub runners.
- [ ] Run `check-release.yml` manually and confirm the chat message arrives.
- [ ] Run `upgrade.yml` manually against the already-deployed version to exercise both gates without changing anything (`install` is `helm upgrade --install` and is idempotent).
- [ ] Watch the first real `push-images` run and record actual `/mnt` usage, so the skopeo fallback threshold is known rather than guessed.
