"""
Tests for MTP Subfolder Path Parsing and Device Resolution (core/mtp_engine.py).
"""
import pytest
from core.mtp_engine import parse_mtp_device_name, parse_mtp_subfolder_path, is_mtp_path

def test_parse_mtp_device_name_with_subfolders():
    assert parse_mtp_device_name("MTP:\\Pixel 8 Pro\\Internal shared storage") == "Pixel 8 Pro"
    assert parse_mtp_device_name("MTP:\\Pixel 8 Pro\\Internal shared storage\\DCIM") == "Pixel 8 Pro"
    assert parse_mtp_device_name("MTP:\\Galaxy S24 Ultra") == "Galaxy S24 Ultra"

def test_parse_mtp_subfolder_path():
    assert parse_mtp_subfolder_path("MTP:\\Pixel 8 Pro\\Internal shared storage") == "Internal shared storage"
    assert parse_mtp_subfolder_path("MTP:\\Pixel 8 Pro\\Internal shared storage\\DCIM") == "Internal shared storage\\DCIM"
    assert parse_mtp_subfolder_path("MTP:\\Galaxy S24 Ultra") == ""

def test_is_mtp_path_subfolders():
    assert is_mtp_path("MTP:\\Pixel 8 Pro\\Internal shared storage") is True
    assert is_mtp_path("MTP:\\Pixel 8 Pro\\DCIM") is True
