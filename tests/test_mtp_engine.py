"""
Tests for MTP Device Support & MTPEngine (core/mtp_engine.py & utils/drive_detector.py).
"""
import pytest
from core.mtp_engine import is_mtp_path, parse_mtp_device_name
from utils.drive_detector import get_available_drives

def test_is_mtp_path():
    assert is_mtp_path("MTP:\\Pixel 8") is True
    assert is_mtp_path("MTP:\\iPhone 15 Pro") is True
    assert is_mtp_path("E:\\DCIM") is False
    assert is_mtp_path("C:\\DEV\\sd_backup") is False

def test_parse_mtp_device_name():
    assert parse_mtp_device_name("MTP:\\Pixel 8") == "Pixel 8"
    assert parse_mtp_device_name("MTP:\\Galaxy S24 Ultra") == "Galaxy S24 Ultra"
    assert parse_mtp_device_name("E:\\") == ""

def test_get_available_drives_structure():
    drives = get_available_drives()
    assert isinstance(drives, list)
    for d in drives:
        assert "path" in d
        assert "drive_type" in d
