"""
Tests for Windows Shell MTP Device Detection & Path Parsing.
"""
import pytest
from core.mtp_engine import MTPEngine, is_mtp_path, parse_mtp_device_name

def test_mtp_detection_logic():
    engine = MTPEngine()
    devices = engine.get_mtp_devices()
    assert isinstance(devices, list)
    
    # Check that any detected MTP devices have valid MTP:\ paths
    for dev in devices:
        assert is_mtp_path(dev["path"])
        assert parse_mtp_device_name(dev["path"]) == dev["label"]

def test_is_mtp_path_variations():
    assert is_mtp_path("MTP:\\Pixel 8 Pro") is True
    assert is_mtp_path("MTP:\\Pixel 8 Pro\\DCIM") is True
    assert is_mtp_path("C:\\DCIM") is False
