"""
Tests for Qt Signal Logging Handler (core/logger.py).
"""
import logging
import pytest
from PySide6.QtCore import QCoreApplication
from core.logger import QtSignalingLogHandler

def test_logger_signal_emission():
    app = QCoreApplication.instance() or QCoreApplication([])
    
    received_logs = []
    
    def log_callback(msg: str, level: str):
        received_logs.append((msg, level))
        
    handler = QtSignalingLogHandler()
    handler.log_emitted.connect(log_callback)
    
    logger = logging.getLogger("test_sd_backup")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    logger.info("Info test message")
    logger.debug("Debug test message")
    logger.error("Error test message")
    
    assert len(received_logs) == 3
    assert received_logs[0] == ("Info test message", "INFO")
    assert received_logs[1] == ("Debug test message", "DEBUG")
    assert received_logs[2] == ("Error test message", "ERROR")
