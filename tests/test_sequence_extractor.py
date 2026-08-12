"""
Tests for Smart Filename Sequence Extractor & Cleaner in utils/path_formatter.py
"""
import pytest
from datetime import datetime
from utils.path_formatter import format_target_filename, extract_sequence_and_clean_stem

def test_extract_dji_timestamp_sequence():
    filename = "DJI_20260811150626_0113_D.MP4"
    cleaned_stem, seq = extract_sequence_and_clean_stem(filename)
    assert seq == "0113"
    assert "20260811150626" not in cleaned_stem
    assert cleaned_stem == "DJI_0113_D"

def test_format_dji_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DJI_20260811150626_0113_D.MP4"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_DJI_0113_D.MP4"

def test_format_dji_filename_with_custom_suffix():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DJI_20260811150626_0113_D.MP4"
    formatted = format_target_filename(dt, filename, suffix="MAVIC")
    assert formatted == "20260811_150626_MAVIC_0113_D.MP4"

def test_format_phone_timestamp_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "IMG_20260811_150626_0452.JPG"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_IMG_0452.JPG"

def test_standard_camera_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DSC00123.JPG"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_DSC00123.JPG"
