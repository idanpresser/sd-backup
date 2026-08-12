"""
Tests for MTPEngine COM CoInitialize and empty MTP device warnings (core/mtp_engine.py & core/worker.py).
"""
import sys
import pytest
from core.mtp_engine import MTPEngine

def test_mtp_engine_coinitialize():
    if sys.platform == "win32":
        import pythoncom
        pythoncom.CoInitialize()
    
    engine = MTPEngine()
    devices = engine.get_mtp_devices()
    assert isinstance(devices, list)
