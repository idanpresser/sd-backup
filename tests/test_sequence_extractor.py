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
    assert "DJI" not in cleaned_stem
    assert cleaned_stem == "0113_D"

def test_format_dji_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DJI_20260811150626_0113_D.MP4"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_0113_D.MP4"

def test_format_dji_filename_with_custom_suffix():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DJI_20260811150626_0113_D.MP4"
    formatted = format_target_filename(dt, filename, suffix="MAVIC")
    assert formatted == "20260811_150626_0113_D_MAVIC.MP4"

def test_format_phone_timestamp_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "IMG_20260811_150626_0452.JPG"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_0452.JPG"

def test_format_phone_timestamp_filename_with_suffix():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "IMG_20260811_150626_0452.JPG"
    formatted = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted == "20260811_150626_0452_IdanPresser(C).JPG"

def test_standard_camera_filename():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DSC00123.JPG"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_00123.JPG"

def test_standard_camera_filename_with_suffix():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "DSC00123.JPG"
    formatted = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted == "20260811_150626_00123_IdanPresser(C).JPG"

def test_pixel_pano_tag_preservation():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "PXL_20260811_150626123.PANO.jpg"
    formatted = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted == "20260811_150626_PANO_IdanPresser(C).jpg"

def test_raw_adobe_prefix_stripping():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "_DSC0123.ARW"
    formatted = format_target_filename(dt, filename, suffix="")
    assert formatted == "20260811_150626_0123.ARW"

def test_empty_stem_after_stripping_fallback():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "IMG_20260811_150626.JPG"
    formatted_no_suffix = format_target_filename(dt, filename, suffix="")
    assert formatted_no_suffix == "20260811_150626.JPG"
    
    formatted_with_suffix = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted_with_suffix == "20260811_150626_IdanPresser(C).JPG"

def test_custom_user_stem_preservation():
    dt = datetime(2026, 8, 11, 15, 6, 26)
    filename = "Custom_Trip_PANO_005.JPG"
    formatted = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted == "20260811_150626_Custom_Trip_PANO_005_IdanPresser(C).JPG"


def test_pixel_timestamp_only_stripping():
    dt = datetime(2026, 8, 17, 15, 16, 4)
    filename = "PXL_20260817_151604782.jpg"
    formatted_no_suffix = format_target_filename(dt, filename, suffix="")
    assert formatted_no_suffix == "20260817_151604.jpg"

    formatted_with_suffix = format_target_filename(dt, filename, suffix="IdanPresser(C)")
    assert formatted_with_suffix == "20260817_151604_IdanPresser(C).jpg"


def test_pixel_long_exposure_and_portrait_variants():
    dt = datetime(2026, 8, 6, 12, 42, 10)
    
    # Long exposure single & pairs
    f1 = format_target_filename(dt, "PXL_20260806_124210009.LONG_EXPOSURE-01.jpg")
    assert f1 == "20260806_124210_LONG_EXPOSURE_01.jpg"

    f2 = format_target_filename(dt, "PXL_20260806_124210009.LONG_EXPOSURE-01.COVER.jpg")
    assert f2 == "20260806_124210_LONG_EXPOSURE_01_COVER.jpg"

    f3 = format_target_filename(dt, "PXL_20260806_124210009.LONG_EXPOSURE-02.ORIGINAL.jpg")
    assert f3 == "20260806_124210_LONG_EXPOSURE_02_ORIGINAL.jpg"

    # Portrait pairs (bokeh cover vs original unblurred)
    p1 = format_target_filename(dt, "PXL_20260806_124210009.PORTRAIT-01.COVER.jpg")
    assert p1 == "20260806_124210_PORTRAIT_01_COVER.jpg"

    p2 = format_target_filename(dt, "PXL_20260806_124210009.PORTRAIT-02.ORIGINAL.jpg")
    assert p2 == "20260806_124210_PORTRAIT_02_ORIGINAL.jpg"


def test_pixel_action_pan_raw_astro_motion():
    dt = datetime(2026, 8, 6, 12, 42, 10)

    # Action pan & RAW DNG
    ap = format_target_filename(dt, "PXL_20260806_124210009.ACTION_PAN-01.COVER.jpg")
    assert ap == "20260806_124210_ACTION_PAN_01_COVER.jpg"

    raw = format_target_filename(dt, "PXL_20260806_124210009.RAW-01.COVER.dng")
    assert raw == "20260806_124210_RAW_01_COVER.dng"

    # Night Sight, Astro, Motion Photo, Cinematic
    night = format_target_filename(dt, "PXL_20260806_124210009.NIGHT.jpg")
    assert night == "20260806_124210_NIGHT.jpg"

    astro = format_target_filename(dt, "PXL_20260806_124210009.ASTRO.mp4")
    assert astro == "20260806_124210_ASTRO.mp4"

    mp = format_target_filename(dt, "PXL_20260806_124210009.MP.jpg")
    assert mp == "20260806_124210_MP.jpg"

    cine = format_target_filename(dt, "PXL_20260806_124210009.CINEMATIC.mp4")
    assert cine == "20260806_124210_CINEMATIC.mp4"



