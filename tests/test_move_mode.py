"""
Tests for Same-Drive auto-detection & instant Move Mode in core/worker.py and drive_detector.py
"""
import os
import pytest
from PySide6.QtCore import QCoreApplication
from core.worker import BackupWorker
from utils.drive_detector import is_same_drive

def test_is_same_drive_matching(tmp_path):
    p1 = str(tmp_path / "folder_a")
    p2 = str(tmp_path / "folder_b")
    assert is_same_drive(p1, p2) is True

def test_is_same_drive_different(tmp_path):
    if os.name == "nt":
        assert is_same_drive("C:\\Source", "D:\\Target") is False
        assert is_same_drive("E:\\DCIM", "D:\\Backup") is False
    else:
        assert is_same_drive("/mnt/drive1/src", "/mnt/drive2/tgt") is False

def test_backup_worker_move_mode(tmp_path):
    src = tmp_path / "SAME_DRIVE_SRC"
    src.mkdir()
    f1 = src / "IMG_0001.JPG"
    f1.write_bytes(b"SAME_DRIVE_MOVE_TEST_DATA_111111111111")
    
    tgt = tmp_path / "SAME_DRIVE_TGT"
    tgt.mkdir()

    app = QCoreApplication.instance() or QCoreApplication([])

    worker = BackupWorker(
        source_card_path=str(src),
        target_dir=str(tgt),
        fastcopy_path="",
        custom_suffix="MOVE_TEST",
        folder_opts={"dcim": True, "private": True, "full_volume": True},
        move_mode=True
    )

    summary = {}
    worker.signals.finished.connect(lambda s: summary.update(s))
    worker.run()

    assert summary.get("scanned") == 1
    assert summary.get("copied") == 1

    # Original file must no longer exist in source directory (moved!)
    assert not os.path.exists(f1)
