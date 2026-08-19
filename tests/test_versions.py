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
