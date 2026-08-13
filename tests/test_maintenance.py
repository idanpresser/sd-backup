"""
Tests for Consolidated Maintenance Engine (utils/maintenance.py).
"""
import os
import sqlite3
import tempfile
import shutil
import pytest

from utils.maintenance import rename_suffix_in_backup, clean_blacklisted_files_in_backup
from core.db import DatabaseManager


@pytest.fixture
def temp_backup_env(tmp_path):
    root_dir = str(tmp_path / "backup_target")
    os.makedirs(root_dir, exist_ok=True)
    db = DatabaseManager(root_dir)
    return root_dir, db


def test_rename_suffix_in_backup(temp_backup_env):
    root_dir, db = temp_backup_env
    
    # Create sample media file on disk
    old_filename = "DSC_0001_AnatKP(C).JPG"
    old_file_path = os.path.join(root_dir, old_filename)
    with open(old_file_path, "w") as f:
        f.write("dummy photo data")

    # Register in DB
    hash_val = "hash_anat_123"
    db.register_file(hash_val, old_filename, old_filename, 100, "2026-08-13T12:00:00", "EXIF")
    db.update_transfer_status(hash_val, old_file_path, old_file_path, "COPIED")
    db.checkpoint()

    # Run maintenance renamer
    stats = rename_suffix_in_backup(root_dir, "AnatKP(C)", "IdanPresser(C)")

    assert stats["renamed_count"] == 1
    assert stats["db_updated_count"] >= 1
    assert not os.path.exists(old_file_path)

    new_file_path = os.path.join(root_dir, "DSC_0001_IdanPresser(C).JPG")
    assert os.path.exists(new_file_path)

    # Check DB update
    assert db.is_file_copied(hash_val)
    status = db.get_transfer_status(hash_val)
    assert status == "COPIED"


def test_clean_blacklisted_files_in_backup(temp_backup_env):
    root_dir, db = temp_backup_env

    # Create blacklisted system file
    bad_file = os.path.join(root_dir, "SONYCARD.IND")
    with open(bad_file, "w") as f:
        f.write("sony index data")

    # Register in DB
    hash_val = "hash_sony_ind"
    db.register_file(hash_val, "SONYCARD.IND", "SONYCARD.IND", 50, "2026-08-13T12:00:00", "MTIME")
    db.update_transfer_status(hash_val, bad_file, bad_file, "COPIED")
    db.checkpoint()

    assert os.path.exists(bad_file)

    # Run blacklist cleaner
    stats = clean_blacklisted_files_in_backup(root_dir)

    assert stats["deleted_count"] == 1
    assert stats["db_removed_count"] >= 1
    assert not os.path.exists(bad_file)
