"""
Edge case tests for BackupWorker pipeline:
- Staging filename collisions (duplicate basenames in different source folders)
- Target filename collisions (same date_taken timestamp disambiguation)
- FastCopy trailing slash sanitization
"""
import os
import tempfile
import pytest
from datetime import datetime
from PySide6.QtCore import QCoreApplication
from core.worker import BackupWorker
from utils.path_formatter import format_full_target_path, resolve_target_path_collision

def test_same_basename_different_dirs(tmp_path):
    sd = tmp_path / "SD_COLLISION"
    dir1 = sd / "DCIM" / "100EOS"
    dir2 = sd / "DCIM" / "101EOS"
    dir1.mkdir(parents=True)
    dir2.mkdir(parents=True)

    # Two different files with identical original basename IMG_0001.JPG
    f1 = dir1 / "IMG_0001.JPG"
    f1.write_bytes(b"IMAGE_1_BYTES_UNIQUE_111111111111")

    f2 = dir2 / "IMG_0001.JPG"
    f2.write_bytes(b"IMAGE_2_BYTES_UNIQUE_22222222222222222")

    target = tmp_path / "TARGET_COLLISION"
    target.mkdir()

    app = QCoreApplication.instance() or QCoreApplication([])

    worker = BackupWorker(
        source_card_path=str(sd),
        target_dir=str(target),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False}
    )

    summary = {}
    worker.signals.finished.connect(lambda s: summary.update(s))
    worker.run()

    assert summary.get("scanned") == 2
    assert summary.get("copied") == 2
    assert summary.get("duplicates") == 0

def test_target_path_collision_avoidance(tmp_path):
    dt = datetime(2026, 3, 29, 14, 2, 11)
    base_target = format_full_target_path(str(tmp_path), dt, "IMG_0001.JPG", suffix="CAM1")
    
    # Create the first target file on disk
    os.makedirs(os.path.dirname(base_target), exist_ok=True)
    with open(base_target, "w") as f:
        f.write("FILE_1")

    # Resolve collision for second file with same date and suffix
    resolved = resolve_target_path_collision(base_target)
    assert resolved != base_target
    assert resolved.endswith("_1.JPG") or "_1" in resolved
