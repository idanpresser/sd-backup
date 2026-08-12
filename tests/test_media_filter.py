"""
Tests for Multi-Layer Media File Filter (utils/media_filter.py).
"""
import pytest
from utils.media_filter import is_media_file, is_blacklisted_system_file

def test_blacklisted_system_files():
    assert is_blacklisted_system_file("IndexerVolumeGuid") is True
    assert is_blacklisted_system_file("WPSettings.dat") is True
    assert is_blacklisted_system_file("SONYCARD.IND") is True
    assert is_blacklisted_system_file("PP-101.db") is True
    assert is_blacklisted_system_file("INDEX.BDM") is True
    assert is_blacklisted_system_file("desktop.ini") is True
    assert is_blacklisted_system_file("thumbs.db") is True
    assert is_blacklisted_system_file("IMG_0001.JPG") is False

def test_media_file_filter_whitelist():
    assert is_media_file("DCIM/100EOS/IMG_0001.JPG") is True
    assert is_media_file("DCIM/100EOS/IMG_0001.CR3") is True
    assert is_media_file("DCIM/100EOS/CLIP_001.MP4") is True
    assert is_media_file("DCIM/100EOS/CLIP_001.MOV") is True
    assert is_media_file("PRIVATE/VOICE/AUDIO_001.WAV") is True

def test_media_file_filter_sidecars():
    assert is_media_file("DCIM/100EOS/GOPRO_001.THM") is True
    assert is_media_file("DCIM/100EOS/GOPRO_001.LRF") is True
    assert is_media_file("DCIM/100EOS/PHOTO.XMP") is True

def test_media_file_filter_system_rejection():
    assert is_media_file("IndexerVolumeGuid") is False
    assert is_media_file("WPSettings.dat") is False
    assert is_media_file("SONYCARD.IND") is False
    assert is_media_file("PP-101.db") is False
    assert is_media_file("INDEX.BDM") is False
    assert is_media_file("AVIN0001.BNP") is False
    assert is_media_file("00011.CPI") is False
