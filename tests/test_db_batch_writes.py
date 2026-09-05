"""
Tests for batched catalog writes (core/db.py).

Every catalog write opened a fresh sqlite connection (each re-running
PRAGMA journal_mode=WAL), costing ~80ms per file across the three writes the
transfer path makes. DatabaseManager.batch() must let a burst of writes share one
connection and one commit, without weakening the register_file() path guard.
"""
import sqlite3

import pytest

from core.db import DatabaseManager


@pytest.fixture
def db(tmp_path):
    return DatabaseManager(str(tmp_path / "archive"))


def _catalog_rows(db):
    with sqlite3.connect(db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM file_catalog").fetchall()]


def test_batch_writes_are_visible_after_the_context_exits(db):
    with db.batch() as conn:
        for i in range(5):
            db.register_file(
                f"hash{i:04d}", f"IMG_{i}.JPG", f"DCIM/IMG_{i}.JPG", 1024,
                "2026-08-30T12:00:00", "EXIF",
                destination_filename=f"20260830_120000_{i}.JPG",
                target_relative_path=f"2026/2026-08/2026-08-30/20260830_120000_{i}.JPG",
                conn=conn,
            )

    rows = _catalog_rows(db)
    assert len(rows) == 5


def test_batch_reuses_a_single_connection(db, monkeypatch):
    opened = []
    real_connect = sqlite3.connect

    def counting_connect(*args, **kwargs):
        opened.append(args[0] if args else kwargs.get("database"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", counting_connect)

    with db.batch() as conn:
        for i in range(10):
            db.register_file(
                f"h{i}", "IMG.JPG", "DCIM/IMG.JPG", 10, "2026-08-30T12:00:00", "EXIF",
                conn=conn,
            )
            db.update_transfer_status(f"h{i}", "src", "dst", "COPIED", conn=conn)
            db.register_metadata(f"h{i}", "IMG.JPG", {"camera_make": "Sony"}, conn=conn)

    assert len(opened) == 1, f"batch opened {len(opened)} connections, expected 1"


def test_batch_still_enforces_the_archive_relative_path_guard(db):
    """The single guarded write path must not be bypassed by the batch route."""
    with db.batch() as conn:
        db.register_file(
            "unsafehash", "IMG.JPG", "DCIM/IMG.JPG", 10, "2026-08-30T12:00:00", "EXIF",
            destination_filename="IMG.JPG",
            target_relative_path=r"C:\Somewhere\Else\IMG.JPG",
            conn=conn,
        )
        db.register_file(
            "escapehash", "IMG2.JPG", "DCIM/IMG2.JPG", 10, "2026-08-30T12:00:00", "EXIF",
            destination_filename="IMG2.JPG",
            target_relative_path=r"..\..\outside\IMG2.JPG",
            conn=conn,
        )

    rows = {r["composite_hash"]: r for r in _catalog_rows(db)}
    assert rows["unsafehash"]["target_relative_path"] is None
    assert rows["escapehash"]["target_relative_path"] is None


def test_writes_without_a_batch_still_work(db):
    """Passing no conn must keep the original per-call connection behaviour."""
    db.register_file(
        "solohash", "IMG.JPG", "DCIM/IMG.JPG", 2048, "2026-08-30T12:00:00", "EXIF",
        destination_filename="out.JPG",
        target_relative_path="2026/2026-08/2026-08-30/out.JPG",
    )
    db.update_transfer_status("solohash", "src", "dst", "COPIED")
    db.register_metadata("solohash", "IMG.JPG", {"camera_make": "Canon"})

    rows = _catalog_rows(db)
    assert len(rows) == 1
    # register_file normalizes to the Windows separator convention used across the catalog.
    assert rows[0]["target_relative_path"] == r"2026\2026-08\2026-08-30\out.JPG"
    assert db.is_file_copied("solohash")
    assert db.get_metadata("solohash")["camera_make"] == "Canon"


def test_batch_rolls_back_on_exception(db):
    with pytest.raises(RuntimeError):
        with db.batch() as conn:
            db.register_file(
                "willroll", "IMG.JPG", "DCIM/IMG.JPG", 10, "2026-08-30T12:00:00", "EXIF",
                conn=conn,
            )
            raise RuntimeError("boom")

    assert _catalog_rows(db) == []
