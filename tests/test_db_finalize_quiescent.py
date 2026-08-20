"""
Regression tests for sd_backup-tz6: after a session ends, the catalog must be left
quiescent — WAL checkpointed into the main file and the -wal/-shm sidecars gone — so
that QuickImageCullLAN, which attaches the catalog with ?mode=ro&immutable=1 (and thus
ignores the WAL entirely), sees every committed row and never reads a torn page.
"""
import os
import sqlite3
import pytest
from core.db import DatabaseManager


def test_finalize_removes_wal_sidecars_and_data_survives(tmp_path):
    target = tmp_path / "BACKUP"
    target.mkdir()
    db = DatabaseManager(str(target))

    db.register_file(
        "hash_tz6", "IMG_0001.ARW", "DCIM/IMG_0001.ARW", 100,
        "2026-03-29T14:02:11", "EXIF",
        destination_filename="20260329_IMG_0001.ARW",
        target_relative_path="2026/2026-03/20260329_IMG_0001.ARW",
    )

    db_path = db.db_path
    wal = db_path + "-wal"
    shm = db_path + "-shm"

    db.finalize()

    assert not os.path.exists(wal), "-wal sidecar must be gone after finalize"
    assert not os.path.exists(shm), "-shm sidecar must be gone after finalize"

    # Read exactly as the culler does: read-only + immutable (WAL is ignored).
    uri = "file:" + db_path.replace("\\", "/") + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute(
            "SELECT target_relative_path FROM file_catalog WHERE composite_hash = ?",
            ("hash_tz6",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, "committed row must be visible to an immutable reader after finalize"
    assert row[0].replace("\\", "/") == "2026/2026-03/20260329_IMG_0001.ARW"


def test_manager_reusable_after_finalize(tmp_path):
    """finalize() must not break the manager: a subsequent write re-enters WAL and works."""
    target = tmp_path / "BACKUP2"
    target.mkdir()
    db = DatabaseManager(str(target))
    db.register_file(
        "h1", "a.jpg", "a.jpg", 1, "2026-01-01T00:00:00", "MTIME",
        destination_filename="a.jpg", target_relative_path="a.jpg",
    )
    db.finalize()

    # New write after finalize should still succeed.
    db.register_file(
        "h2", "b.jpg", "b.jpg", 2, "2026-01-02T00:00:00", "MTIME",
        destination_filename="b.jpg", target_relative_path="b.jpg",
    )
    with db._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM file_catalog").fetchone()[0]
    assert n == 2
