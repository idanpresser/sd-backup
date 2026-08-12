"""
Tests for drive_detector module.
"""
import pytest
import os
from utils.drive_detector import get_available_drives, get_drive_volume_info

def test_get_available_drives():
    drives = get_available_drives()
    assert isinstance(drives, list)
    for drive in drives:
        assert "path" in drive
        assert "label" in drive
        assert "drive_type" in drive
        assert "free_bytes" in drive
        assert "total_bytes" in drive

def test_get_drive_volume_info_nonexistent():
    info = get_drive_volume_info("Z:\\NonExistentDrivePath123")
    assert info["label"] == "" or info["label"] == "Unknown"
    assert info["serial"] == "" or info["serial"] == "UNKNOWN"
