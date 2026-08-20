"""
Tests for sd_backup-a4i (CLI): the rescan flags parse correctly and default off.
"""
from main import parse_args


def test_defaults_off():
    a = parse_args([])
    assert a.rescan_after_import is False
    assert a.rescan_full_drive is False


def test_rescan_after_import_flag():
    a = parse_args(["--rescan-target-after-import"])
    assert a.rescan_after_import is True
    assert a.rescan_full_drive is False


def test_sync_on_finish_alias():
    a = parse_args(["--sync-on-finish"])
    assert a.rescan_after_import is True


def test_full_drive_flag():
    a = parse_args(["--rescan-full-drive"])
    assert a.rescan_full_drive is True


def test_ignores_unknown_qt_args():
    a = parse_args(["--rescan-target-after-import", "-platform", "offscreen"])
    assert a.rescan_after_import is True
