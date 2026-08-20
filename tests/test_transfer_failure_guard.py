"""
Regression tests for sd_backup-w6i: the copy loops must not catalog a file as
COPIED when the destination file does not actually exist on disk (e.g. card pulled
mid-copy, staging failure, I/O error). A missing destination must be recorded as
FAILED and surfaced as a read_error, never as a COPIED catalog row.
"""
import os
import pytest
from core.worker import BackupWorker
from core.db import DatabaseManager


def _make_worker(source_dir, target_dir):
    return BackupWorker(
        source_card_path=str(source_dir),
        target_dir=str(target_dir),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False},
    )


def test_missing_destination_records_failed_not_copied(tmp_path):
    """A finalize call for a destination that was never written must not create a
    COPIED catalog row; it records FAILED and returns False."""
    source = tmp_path / "SRC"
    source.mkdir()
    target = tmp_path / "TARGET"
    target.mkdir()

    db = DatabaseManager(str(target))
    worker = _make_worker(source, target)

    errors = []
    worker.signals.read_error.connect(lambda name, detail: errors.append((name, detail)))

    missing_dst = os.path.join(str(target), "2026", "2026-03", "IMG_9999.JPG")
    src_p = os.path.join(str(source), "IMG_9999.JPG")  # also does not exist

    ok = worker._finalize_transfer(
        db,
        resolved_dst_p=missing_dst,
        h_val="deadbeef_hash",
        orig_basename="IMG_9999.JPG",
        rel_p="IMG_9999.JPG",
        f_size=1234,
        dt_iso="2026-03-29T14:02:11",
        src_type="MTIME",
        src_p=src_p,
    )

    assert ok is False, "finalize must report failure when the destination is missing"

    # A missing destination must never be cataloged as COPIED, and must not leave any
    # file_catalog row behind (which the culler would otherwise try to serve).
    assert db.get_transfer_status("deadbeef_hash") != "COPIED"
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM file_catalog WHERE composite_hash = ?", ("deadbeef_hash",)
        ).fetchone()
    assert row is None, "a missing-destination file must not be cataloged"
    assert errors, "a read_error signal must be emitted for the failed transfer"


def test_present_destination_records_copied(tmp_path):
    """When the destination file exists, finalize catalogs it as COPIED and returns True."""
    source = tmp_path / "SRC"
    source.mkdir()
    target = tmp_path / "TARGET"
    target.mkdir()

    db = DatabaseManager(str(target))
    worker = _make_worker(source, target)

    dst_dir = os.path.join(str(target), "2026", "2026-03")
    os.makedirs(dst_dir, exist_ok=True)
    real_dst = os.path.join(dst_dir, "IMG_0001.JPG")
    with open(real_dst, "wb") as f:
        f.write(b"REAL_IMAGE_BYTES")

    ok = worker._finalize_transfer(
        db,
        resolved_dst_p=real_dst,
        h_val="livehash",
        orig_basename="IMG_0001.JPG",
        rel_p="IMG_0001.JPG",
        f_size=16,
        dt_iso="2026-03-29T14:02:11",
        src_type="MTIME",
        src_p=os.path.join(str(source), "IMG_0001.JPG"),
    )

    assert ok is True
    assert db.get_transfer_status("livehash") == "COPIED"
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT target_relative_path FROM file_catalog WHERE composite_hash = ?",
            ("livehash",),
        ).fetchone()
    assert row is not None
