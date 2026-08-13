"""
Tests for DB-Disk Sync Engine (core/sync_engine.py) using TDD.
"""
import os
import sqlite3
import tempfile
import shutil
import pytest

from core.sync_engine import calculate_sync_diff, execute_sync
from core.db import DatabaseManager
from core.metadata import MetadataExtractor


@pytest.fixture
def temp_sync_env(tmp_path):
    root_dir = str(tmp_path / "sync_target")
    os.makedirs(root_dir, exist_ok=True)
    db = DatabaseManager(root_dir)
    return root_dir, db


def test_sync_engine_detects_missing_and_uncataloged(temp_sync_env):
    root_dir, db = temp_sync_env

    # 1. Register a record in DB whose file is missing on disk
    missing_hash = "missing_file_hash_999"
    missing_path = os.path.join(root_dir, "2026/08/13/GHOST_PHOTO.JPG")
    db.register_file(missing_hash, "GHOST_PHOTO.JPG", "2026/08/13/GHOST_PHOTO.JPG", 1000, "2026-08-13T12:00:00", "EXIF")
    db.update_transfer_status(missing_hash, "E:/GHOST_PHOTO.JPG", missing_path, "COPIED")
    db.checkpoint()

    # 2. Place a real file on disk that is NOT in DB
    real_file_rel = "2026/08/13/NEW_UNTRACKED.JPG"
    real_file_abs = os.path.join(root_dir, real_file_rel)
    os.makedirs(os.path.dirname(real_file_abs), exist_ok=True)
    with open(real_file_abs, "w") as f:
        f.write("untracked image content")

    # Calculate sync diff
    diff = calculate_sync_diff(root_dir)

    assert len(diff["missing_records"]) == 1
    assert diff["missing_records"][0]["composite_hash"] == missing_hash

    assert len(diff["uncataloged_files"]) == 1
    assert os.path.basename(diff["uncataloged_files"][0]["file_path"]) == "NEW_UNTRACKED.JPG"


def test_sync_engine_executes_sync(temp_sync_env):
    root_dir, db = temp_sync_env

    # Setup missing record and uncataloged file
    missing_hash = "missing_hash_777"
    missing_path = os.path.join(root_dir, "MISSING_PIC.JPG")
    db.register_file(missing_hash, "MISSING_PIC.JPG", "MISSING_PIC.JPG", 500, "2026-01-01T00:00:00", "MTIME")
    db.update_transfer_status(missing_hash, "E:/MISSING_PIC.JPG", missing_path, "COPIED")

    untracked_abs = os.path.join(root_dir, "UNTRACKED_CLIP.MP4")
    with open(untracked_abs, "w") as f:
        f.write("untracked video data")
    db.checkpoint()

    # Execute sync with default ADD_TO_DB
    stats = execute_sync(root_dir, remove_missing=True, uncataloged_action="ADD_TO_DB")

    assert stats["removed_records"] == 1
    assert stats["added_records"] == 1
    assert not db.is_file_copied(missing_hash)

    # Verify untracked file was indexed into catalog
    comp_hash, _, _, _ = MetadataExtractor.compute_composite_hash(untracked_abs)
    assert db.is_file_copied(comp_hash)


def test_sync_engine_deletes_uncataloged_disk_files(temp_sync_env):
    root_dir, db = temp_sync_env

    # Place a garbage / uncataloged file on target disk
    junk_path = os.path.join(root_dir, "LEFTOVER_JUNK.JPG")
    with open(junk_path, "w") as f:
        f.write("junk data to remove")

    assert os.path.exists(junk_path)

    # Execute sync with DELETE_FROM_DISK action
    stats = execute_sync(root_dir, remove_missing=False, uncataloged_action="DELETE_FROM_DISK")

    assert stats["deleted_disk_files"] == 1
    assert not os.path.exists(junk_path)

