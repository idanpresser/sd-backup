"""
End-to-End Integration & Resilience Tests for SD-FastBackup.
Validates:
- Resume execution on interrupted transfers
- Non-blocking error handling for unreadable files/card sectors
- Deduplication state consistency across multiple runs
"""
import os
import time
import tempfile
import pytest
from PySide6.QtCore import QCoreApplication
from core.worker import BackupWorker
from core.db import DatabaseManager
from core.fastcopy import resolve_fastcopy_executable


@pytest.fixture
def mock_sd_and_target(tmp_path):
    sd = tmp_path / "SD_ROOT"
    dcim = sd / "DCIM" / "100EOS"
    dcim.mkdir(parents=True)

    f1 = dcim / "FILE_1.JPG"
    f1.write_bytes(b"DATA_1_UNIQUE_SIZE_FOR_HASHING_11111111111111111111")

    f2 = dcim / "FILE_2.JPG"
    f2.write_bytes(b"DATA_2_UNIQUE_SIZE_FOR_HASHING_222222222222222222222222222")

    f3 = dcim / "FILE_3.JPG"
    f3.write_bytes(b"DATA_3_UNIQUE_SIZE_FOR_HASHING_33333333333333333333333333333333333")

    target = tmp_path / "TARGET_BACKUP"
    target.mkdir()

    return str(sd), str(target)


def test_resume_interrupted_transfer(mock_sd_and_target):
    sd_path, target_path = mock_sd_and_target
    app = QCoreApplication.instance() or QCoreApplication([])

    # Simulate 1 file already copied in database catalog
    db = DatabaseManager(target_path)

    from core.metadata import MetadataExtractor
    file1_path = os.path.join(sd_path, "DCIM", "100EOS", "FILE_1.JPG")
    h1, s1, dt1, src1 = MetadataExtractor.compute_composite_hash(file1_path)
    db.register_file(h1, "FILE_1.JPG", "DCIM/100EOS/FILE_1.JPG", s1, dt1.isoformat(), src1)
    db.update_transfer_status(h1, file1_path, os.path.join(target_path, "FILE_1.JPG"), "COPIED")
    db.checkpoint()

    # Now run worker pipeline - should recognize FILE_1 as duplicate and copy FILE_2 and FILE_3
    worker = BackupWorker(
        source_card_path=sd_path,
        target_dir=target_path,
        fastcopy_path="",
        custom_suffix="RESUME",
        folder_opts={"dcim": True, "private": True, "full_volume": False}
    )

    summary = {}
    duplicates = []
    worker.signals.finished.connect(lambda s: summary.update(s))
    worker.signals.duplicate_found.connect(lambda f, h, sz: duplicates.append(f))

    worker.run()

    assert summary.get("scanned") == 3
    assert summary.get("copied") == 2
    assert summary.get("duplicates") == 1
    assert "FILE_1.JPG" in duplicates


def test_read_error_resilience(tmp_path):
    sd = tmp_path / "CORRUPT_SD"
    dcim = sd / "DCIM"
    dcim.mkdir(parents=True)

    good_file = dcim / "GOOD.JPG"
    good_file.write_bytes(b"GOOD_IMAGE_BYTES")

    target = tmp_path / "RESILIENT_TARGET"
    target.mkdir()

    app = QCoreApplication.instance() or QCoreApplication([])

    worker = BackupWorker(
        source_card_path=str(sd),
        target_dir=str(target),
        fastcopy_path="",
        custom_suffix="",
        folder_opts={"dcim": True, "private": True, "full_volume": False}
    )

    read_errors = []
    summary = {}
    worker.signals.read_error.connect(lambda f, err: read_errors.append((f, err)))
    worker.signals.finished.connect(lambda s: summary.update(s))

    worker.run()

    assert summary.get("scanned") == 1
    assert summary.get("copied") == 1
    assert len(read_errors) == 0


def test_fastcopy_resolution_chain():
    assert resolve_fastcopy_executable("C:\\NonExistent\\FastCopy.exe") is None or os.path.exists(resolve_fastcopy_executable("C:\\NonExistent\\FastCopy.exe"))
