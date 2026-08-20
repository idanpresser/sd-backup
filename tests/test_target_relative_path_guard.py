"""
Tests for sd_backup-vmp: target_relative_path must always be stored as a safe
archive-relative path. QuickImageCullLAN joins archive_root / target_relative_path and
rejects any row whose path is absolute, drive-lettered, UNC, or contains '..' (its
containment check) — such rows silently become un-cullable. register_file is the single
write choke point and must never persist a poison path.
"""
import pytest
from core.db import DatabaseManager
from utils.path_formatter import is_safe_relative_path


@pytest.mark.parametrize("good", [
    "2026/2026-03/_DSC5891.ARW",
    "2026\\2026-03\\_DSC5891.ARW",
    "IMG_0001.JPG",
    "a/b/c/d.mp4",
])
def test_is_safe_relative_path_accepts_relative(good):
    assert is_safe_relative_path(good) is True


@pytest.mark.parametrize("bad", [
    "",
    "D:\\Backups\\x.jpg",
    "C:/Backups/x.jpg",
    "/etc/passwd",
    "\\\\server\\share\\x.jpg",
    "//server/share/x.jpg",
    "../secret.jpg",
    "2026/../../etc/passwd",
    "\\leading\\sep.jpg",
])
def test_is_safe_relative_path_rejects_unsafe(bad):
    assert is_safe_relative_path(bad) is False


def _read_target_rel(db, h):
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT target_relative_path FROM file_catalog WHERE composite_hash = ?", (h,)
        ).fetchone()
    return row["target_relative_path"] if row else "<<missing>>"


def test_register_file_stores_clean_relative_path(tmp_path):
    db = DatabaseManager(str(tmp_path / "T"))
    db.register_file(
        "h_ok", "x.arw", "DCIM/x.arw", 1, "2026-03-29T00:00:00", "EXIF",
        destination_filename="x.arw", target_relative_path="2026/2026-03/x.arw",
    )
    stored = _read_target_rel(db, "h_ok")
    assert stored not in (None, "<<missing>>")
    assert is_safe_relative_path(stored)


def test_register_file_rejects_absolute_path(tmp_path):
    db = DatabaseManager(str(tmp_path / "T2"))
    db.register_file(
        "h_abs", "x.arw", "DCIM/x.arw", 1, "2026-03-29T00:00:00", "EXIF",
        destination_filename="x.arw", target_relative_path="D:\\Backups\\2026\\x.arw",
    )
    # The row still exists, but the poison absolute path must not be persisted.
    assert _read_target_rel(db, "h_abs") is None


def test_register_file_rejects_parent_escape(tmp_path):
    db = DatabaseManager(str(tmp_path / "T3"))
    db.register_file(
        "h_esc", "x.arw", "DCIM/x.arw", 1, "2026-03-29T00:00:00", "EXIF",
        destination_filename="x.arw", target_relative_path="../../etc/passwd",
    )
    assert _read_target_rel(db, "h_esc") is None
