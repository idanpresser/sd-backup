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
