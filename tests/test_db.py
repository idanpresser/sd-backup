"""
Tests for SQLite Database Manager (core/db.py).
"""
import os
import tempfile
import pytest
import shutil
from core.db import DatabaseManager

@pytest.fixture
def temp_target_dir():
    tmpdir = tempfile.mkdtemp()
    yield tmpdir
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass

def test_db_initialization(temp_target_dir):
    db = DatabaseManager(temp_target_dir)
    assert os.path.exists(os.path.join(temp_target_dir, ".sd_backup_catalog.db"))
    db.checkpoint()

def test_register_and_check_volume(temp_target_dir):
    db = DatabaseManager(temp_target_dir)
    db.register_volume("12345678", "TEST_SD")
    db.register_volume("12345678", "TEST_SD_UPDATED")
    db.checkpoint()

def test_file_catalog_and_deduplication(temp_target_dir):
    db = DatabaseManager(temp_target_dir)
    hash_val = "abc123hash"
    
    assert not db.is_file_copied(hash_val)
    
    db.register_file(
        composite_hash=hash_val,
        filename="IMG_0001.JPG",
        rel_path="DCIM/100MSDCF/IMG_0001.JPG",
        size=5000000,
        date_taken="2026-03-29T14:02:11",
        source="EXIF"
    )
    
    assert not db.is_file_copied(hash_val)  # registered but not copied yet
    
    db.update_transfer_status(hash_val, "E:/DCIM/IMG_0001.JPG", "D:/Target/2026/03/29/IMG_0001.JPG", "COPIED")
    assert db.is_file_copied(hash_val)
    db.checkpoint()

def test_transfer_manifest_statuses(temp_target_dir):
    db = DatabaseManager(temp_target_dir)
    hash_val = "hash_failed_test"
    db.register_file(hash_val, "CLIP.MP4", "PRIVATE/CLIP.MP4", 1000, "2026-01-01T00:00:00", "MTIME")
    
    db.update_transfer_status(hash_val, "E:/PRIVATE/CLIP.MP4", "D:/Target/CLIP.MP4", "FAILED")
    assert db.get_transfer_status(hash_val) == "FAILED"
    assert not db.is_file_copied(hash_val)
    
    failed_items = db.get_failed_transfers()
    assert len(failed_items) == 1
    assert failed_items[0]["composite_hash"] == hash_val
    db.checkpoint()
