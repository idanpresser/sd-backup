"""
Tests for sd_backup-wpn: the catalog publishes a monotonic generation marker so a
consumer (QuickImageCullLAN) can cheaply detect that the catalog changed and re-open
its immutable attachment. The marker must only become visible to an immutable reader
after the corresponding rows are checkpointed (finalize), so a consumer that sees a new
generation is guaranteed to see the rows behind it.
"""
import sqlite3
import pytest
from core.db import DatabaseManager


def test_generation_starts_at_zero_and_is_monotonic(tmp_path):
    target = tmp_path / "BK"
    target.mkdir()
    db = DatabaseManager(str(target))

    assert db.get_generation() == 0

    g1 = db.bump_generation()
    assert g1 == 1
    assert db.get_generation() == 1

    g2 = db.bump_generation()
    assert g2 == 2
    assert db.get_generation() == 2


def test_bump_sets_last_import_timestamp(tmp_path):
    target = tmp_path / "BK2"
    target.mkdir()
    db = DatabaseManager(str(target))
    db.bump_generation()
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM catalog_meta WHERE key = 'last_import'"
        ).fetchone()
    assert row is not None and row["value"]


def test_generation_visible_to_immutable_reader_after_finalize(tmp_path):
    """The consumer reads with immutable=1; the bumped generation must be visible to it
    once the session finalizes (rows + marker checkpointed together)."""
    target = tmp_path / "BK3"
    target.mkdir()
    db = DatabaseManager(str(target))

    db.register_file(
        "h_gen", "IMG.ARW", "IMG.ARW", 10, "2026-03-29T14:02:11", "EXIF",
        destination_filename="IMG.ARW", target_relative_path="2026/IMG.ARW",
    )
    db.bump_generation()
    db.finalize()

    uri = "file:" + db.db_path.replace("\\", "/") + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    try:
        gen = conn.execute(
            "SELECT value FROM catalog_meta WHERE key = 'generation'"
        ).fetchone()
        cnt = conn.execute("SELECT COUNT(*) FROM file_catalog").fetchone()
    finally:
        conn.close()
    assert gen is not None and int(gen[0]) == 1
    assert cnt[0] == 1  # the row behind the generation is visible too
