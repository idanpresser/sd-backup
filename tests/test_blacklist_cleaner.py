"""
Tests for Blacklist Cleaner Helper (utils/blacklist_cleaner.py).
"""
import os
import pytest
from core.db import DatabaseManager
from utils.blacklist_cleaner import clean_blacklisted_files_in_backup

def test_clean_blacklisted_files(tmp_path):
    root_dir = tmp_path / "CLEAN_ROOT"
    root_dir.mkdir()

    sub = root_dir / "2026" / "2026-08" / "2026-08-12"
    sub.mkdir(parents=True)

    # Valid media file
    f_media = sub / "20260812_150000_CAM1_0001.JPG"
    f_media.write_bytes(b"MEDIA_DATA")

    # Blacklisted system files
    f_bad1 = sub / "20260812_150100_IndexerVolumeGuid"
    f_bad1.write_bytes(b"BAD_DATA_1")

    f_bad2 = sub / "20260812_150200_WPSettings.dat"
    f_bad2.write_bytes(b"BAD_DATA_2")

    db = DatabaseManager(str(root_dir))
    db.register_file("h_media", "0001.JPG", "DCIM/0001.JPG", 10, "2026-08-12T15:00:00", "EXIF")
    db.register_file("h_bad1", "IndexerVolumeGuid", "IndexerVolumeGuid", 10, "2026-08-12T15:01:00", "FILE")
    db.register_file("h_bad2", "WPSettings.dat", "WPSettings.dat", 10, "2026-08-12T15:02:00", "FILE")

    db.update_transfer_status("h_media", "E:/0001.JPG", str(f_media), "COPIED")
    db.update_transfer_status("h_bad1", "E:/IndexerVolumeGuid", str(f_bad1), "COPIED")
    db.update_transfer_status("h_bad2", "E:/WPSettings.dat", str(f_bad2), "COPIED")
    db.checkpoint()

    stats = clean_blacklisted_files_in_backup(str(root_dir))

    assert stats["deleted_count"] == 2
    assert os.path.exists(f_media)
    assert not os.path.exists(f_bad1)
    assert not os.path.exists(f_bad2)

    # Check DB record removed
    assert not db.is_file_copied("h_bad1")
    assert db.is_file_copied("h_media") is True
