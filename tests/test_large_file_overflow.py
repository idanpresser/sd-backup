"""
Test for large file byte counts (>2GB) to prevent Shiboken 32-bit int OverflowError.
"""
import pytest
from PySide6.QtCore import QCoreApplication
from core.worker import WorkerSignals

def test_large_byte_count_signal():
    app = QCoreApplication.instance() or QCoreApplication([])
    signals = WorkerSignals()
    
    received_bytes = 0
    
    def on_transfer_started(total_files, total_bytes):
        nonlocal received_bytes
        received_bytes = total_bytes
        
    signals.transfer_started.connect(on_transfer_started)
    
    # 15 GB byte count (exceeds 32-bit signed int max of 2,147,483,647)
    large_bytes = 15_041_261_487
    signals.transfer_started.emit(10, large_bytes)
    
    assert received_bytes == large_bytes
