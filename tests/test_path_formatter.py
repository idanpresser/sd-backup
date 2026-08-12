"""
Tests for path_formatter module.
"""
import pytest
from datetime import datetime
from utils.path_formatter import (
    format_target_relative_dir,
    format_target_filename,
    format_full_target_path,
    sanitize_path
)

def test_format_target_relative_dir():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    rel_dir = format_target_relative_dir(dt)
    assert rel_dir.replace("\\", "/") == "2026/2026-03/2026-03-29"

def test_format_target_filename_with_suffix():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    name = format_target_filename(dt, "IMG_0001.JPG", suffix="CAM1")
    assert name == "20260329_140211_CAM1.JPG"

def test_format_target_filename_without_suffix():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    name = format_target_filename(dt, "IMG_0001.JPG", suffix="")
    assert name == "20260329_140211_IMG_0001.JPG"

def test_format_full_target_path():
    dt = datetime(2026, 3, 29, 14, 2, 11)
    full_path = format_full_target_path("/backup/root", dt, "CLIP_100.MP4", suffix="A7S3")
    assert full_path.replace("\\", "/").endswith("2026/2026-03/2026-03-29/20260329_140211_A7S3.MP4")

def test_sanitize_path():
    dirty = 'bad/path:name*?<>"|file.txt'
    clean = sanitize_path(dirty)
    for bad_char in '<>:"|?*':
        assert bad_char not in clean
