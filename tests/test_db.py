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

def test_register_and_get_metadata(temp_target_dir):
    db = DatabaseManager(temp_target_dir)
    hash_val = "meta_test_hash_123"
    db.register_file(hash_val, "DSC_0001.JPG", "DCIM/DSC_0001.JPG", 1234567, "2026-05-10T12:00:00", "EXIF")

    sample_meta = {
        "camera_make": "Sony",
        "camera_model": "ILCE-7RM4",
        "lens_model": "FE 24-70mm F2.8 GM",
        "serial_number": "3012345",
        "iso": 100,
        "aperture": "f/2.8",
        "shutter_speed": "1/500",
        "focal_length": "50.0mm",
        "white_balance": "Auto",
        "width": 9504,
        "height": 6336,
        "aspect_ratio": "9504:6336",
        "color_space": "sRGB",
        "video_codec": None,
        "container_format": None,
        "frame_rate": None,
        "duration_seconds": None,
        "bitrate": None,
        "audio_codec": None,
        "audio_channels": None,
        "audio_sample_rate": None,
        "latitude": 37.7749,
        "longitude": -122.4194,
        "altitude": 15.0,
        "raw_json": '{"Image Make": "Sony", "Image Model": "ILCE-7RM4"}'
    }

    db.register_metadata(hash_val, "DSC_0001.JPG", sample_meta)
    res = db.get_metadata(hash_val)
    
    assert res is not None
    assert res["composite_hash"] == hash_val
    assert res["original_filename"] == "DSC_0001.JPG"
    assert res["camera_make"] == "Sony"
    assert res["camera_model"] == "ILCE-7RM4"
    assert res["iso"] == 100
    assert res["aperture"] == "f/2.8"
    assert res["shutter_speed"] == "1/500"
    assert res["latitude"] == 37.7749
    assert res["raw_json"] == '{"Image Make": "Sony", "Image Model": "ILCE-7RM4"}'
    db.checkpoint()


def test_backfill_missing_metadata(temp_target_dir):
    db = DatabaseManager(temp_target_dir)

    # 1. Create a dummy file on disk
    dummy_path = os.path.join(temp_target_dir, "LEGACY_PIC.JPG")
    with open(dummy_path, "w") as f:
        f.write("dummy photo content")

    # 2. Register in DB without file_metadata entry (simulating old cataloged file)
    legacy_hash = "legacy_hash_555"
    db.register_file(legacy_hash, "LEGACY_PIC.JPG", "LEGACY_PIC.JPG", len("dummy photo content"), "2026-08-01T10:00:00", "MTIME")
    db.update_transfer_status(legacy_hash, "E:/LEGACY_PIC.JPG", dummy_path, "COPIED")
    db.checkpoint()

    assert db.get_metadata(legacy_hash) is None

    # 3. Run backfill
    count = db.backfill_missing_metadata()

    assert count == 1
    meta = db.get_metadata(legacy_hash)
    assert meta is not None
    assert meta["composite_hash"] == legacy_hash
    assert meta["original_filename"] == "LEGACY_PIC.JPG"


