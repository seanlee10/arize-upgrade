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
