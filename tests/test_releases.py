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


def test_emphasis_markers_survive_parsing():
    sample_with_breaking_change = """\
# Release 11.40.0 (2026-07-21)

## Upgrade Notes

* ***Breaking Change***: pin your storage classes first.

## Updates

* Some update
"""
    releases = parse_releases(sample_with_breaking_change)
    assert len(releases) == 1
    assert "***Breaking Change***" in releases[0].upgrade_notes


def test_real_fixture_11_40_0_has_breaking_change_marker():
    releases = parse_releases(FIXTURE)
    by_version = {str(r.version): r for r in releases}
    assert "11.40.0" in by_version
    assert "***Breaking Change***" in by_version["11.40.0"].upgrade_notes
