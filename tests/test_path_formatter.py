"""
Tests for path_formatter module.
"""
import pytest
import os
import sys
from datetime import datetime
from utils.path_formatter import (
    format_target_relative_dir,
    format_target_filename,
    format_full_target_path,
    sanitize_path,
    normalize_win_path
)

def test_normalize_win_path():
    mixed = "C:/DEV/sd_backup/DCIM/100EOS/IMG_0001.JPG"
    normalized = normalize_win_path(mixed)
    if sys.platform == "win32" or os.name == "nt":
        assert "/" not in normalized
        assert "\\" in normalized

def test_format_target_relative_dir():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    rel_dir = format_target_relative_dir(dt)
    if sys.platform == "win32" or os.name == "nt":
        assert rel_dir == "2026\\2026-03\\2026-03-29"
    else:
        assert rel_dir.replace("\\", "/") == "2026/2026-03/2026-03-29"

def test_format_target_filename_with_suffix():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    name = format_target_filename(dt, "IMG_0001.JPG", suffix="CAM1")
    assert name == "20260329_140211_0001_CAM1.JPG"

def test_format_full_target_path_with_stack_subfolder():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    # Original relative path contains stack folder PANO
    rel_src = os.path.join("DCIM", "100EOS", "PANO", "IMG_0001.JPG")
    full_path = format_full_target_path("C:\\Backup", dt, "IMG_0001.JPG", suffix="A7S3", original_rel_path=rel_src)
    assert "PANO" in full_path
    if sys.platform == "win32" or os.name == "nt":
        assert "/" not in full_path
        assert full_path == "C:\\Backup\\2026\\2026-03\\2026-03-29\\PANO\\20260329_140211_0001_A7S3.JPG"

def test_sanitize_path():
    dirty = 'bad/path:name*?<>"|file.txt'
    clean = sanitize_path(dirty)
    for bad_char in '<>:"|?*':
        assert bad_char not in clean
