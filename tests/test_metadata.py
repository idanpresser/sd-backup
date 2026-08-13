"""
Tests for Metadata Extractor & Composite Hasher (core/metadata.py).
"""
import os
import hashlib
import tempfile
import pytest
from datetime import datetime
from core.metadata import MetadataExtractor

@pytest.fixture
def sample_file(tmp_path):
    p = tmp_path / "test_file.txt"
    p.write_text("Hello SD Card Backup")
    return str(p)

def test_get_file_size(sample_file):
    size = MetadataExtractor.get_file_size(sample_file)
    assert size > 0
    assert size == os.path.getsize(sample_file)

def test_fallback_mtime_extraction(sample_file):
    dt, source = MetadataExtractor.extract_date_taken(sample_file)
    assert isinstance(dt, datetime)
    assert source == "MTIME"

def test_composite_hash_calculation(sample_file):
    composite_hash, size, dt, source = MetadataExtractor.compute_composite_hash(sample_file)
    assert len(composite_hash) == 64  # SHA256 length in hex
    iso_date = dt.strftime("%Y-%m-%dT%H:%M:%S")
    expected_hash = hashlib.sha256(f"{iso_date}_{size}".encode('utf-8')).hexdigest()
    assert composite_hash == expected_hash
    assert source in ["EXIF", "MEDIAINFO", "MTIME"]

def test_pil_exif_image_metadata_extraction(tmp_path):
    from PIL import Image

    img_path = str(tmp_path / "TEST_EXIF_IMAGE.JPG")
    img = Image.new('RGB', (1920, 1080), color='blue')

    # Create EXIF dictionary using Pillow Exif
    exif = img.getexif()
    exif[271] = "Sony"                # Make
    exif[272] = "ILCE-7RM4"           # Model
    exif[42036] = "FE 24-70mm F2.8 GM" # LensModel
    exif[34855] = 400                 # ISOSpeedRatings
    exif[33437] = 2.8                 # FNumber
    exif[33434] = (1, 1000)           # ExposureTime (1/1000)
    exif[37386] = (50, 1)             # FocalLength (50mm)
    img.save(img_path, exif=exif)

    meta = MetadataExtractor.extract_full_metadata(img_path)

    assert meta["camera_make"] == "Sony"
    assert meta["camera_model"] == "ILCE-7RM4"
    assert meta["lens_model"] == "FE 24-70mm F2.8 GM"
    assert meta["iso"] == 400
    assert meta["aperture"] == "f/2.8"
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["raw_json"] != "{}"


