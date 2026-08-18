"""
Tests for BackupWorker QThread execution pipeline (core/worker.py).
"""
import os
import tempfile
import pytest
from PySide6.QtCore import QCoreApplication
from core.worker import BackupWorker, WorkerSignals

@pytest.fixture
def test_environment(tmp_path):
    src = tmp_path / "sd_card"
    src.mkdir()
    dcim = src / "DCIM" / "100EOS"
    dcim.mkdir(parents=True)
    
    f1 = dcim / "IMG_0001.JPG"
    f1.write_bytes(b"FAKE_EXIF_IMAGE_DATA_1")
    
    f2 = dcim / "IMG_0002.JPG"
    f2.write_bytes(b"FAKE_EXIF_IMAGE_DATA_2_DIFFERENT_PAYLOAD")
    
    dst = tmp_path / "backup_target"
    dst.mkdir()
    
    return str(src), str(dst)

def test_backup_worker_pipeline(test_environment):
    src_dir, dst_dir = test_environment
    
    app = QCoreApplication.instance() or QCoreApplication([])
    
    worker = BackupWorker(
        source_card_path=src_dir,
        target_dir=dst_dir,
        fastcopy_path="",
        custom_suffix="TEST",
        folder_opts={"dcim": True, "private": True, "full_volume": False}
    )
    
    finished_summary = {}
    duplicates_reported = []
    
    def on_finished(summary):
        nonlocal finished_summary
        finished_summary = summary
        
    def on_duplicate(name, hash_val, size):
        duplicates_reported.append((name, hash_val, size))
        
    worker.signals.finished.connect(on_finished)
    worker.signals.duplicate_found.connect(on_duplicate)
    
    # Synchronously run worker loop
    worker.run()
    
    assert finished_summary.get("scanned") == 2
    assert finished_summary.get("copied") == 2
    assert finished_summary.get("duplicates") == 0
    
    # Run again to test deduplication
    worker_again = BackupWorker(
        source_card_path=src_dir,
        target_dir=dst_dir,
        fastcopy_path="",
        custom_suffix="TEST",
        folder_opts={"dcim": True, "private": True, "full_volume": False}
    )
    
    finished_summary_2 = {}
    worker_again.signals.finished.connect(lambda s: finished_summary_2.update(s))
    worker_again.signals.duplicate_found.connect(on_duplicate)
    
    worker_again.run()
    
    assert finished_summary_2.get("scanned") == 2
    assert finished_summary_2.get("copied") == 0
    assert finished_summary_2.get("duplicates") == 2
    assert len(duplicates_reported) == 2

    # Verify Database records:
    # 1. transfer_manifest must contain EXACTLY 2 rows (COPIED) - ZERO DUPLICATE_SKIPPED rows written!
    # 2. file_catalog must preserve original_filename and set destination_filename / target_relative_path
    from core.db import DatabaseManager
    db = DatabaseManager(dst_dir)
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transfer_manifest")
        manifest_rows = [dict(r) for r in cursor.fetchall()]
        assert len(manifest_rows) == 2
        for r in manifest_rows:
            assert r["copy_status"] == "COPIED"

        cursor.execute("SELECT * FROM file_catalog")
        catalog_rows = [dict(r) for r in cursor.fetchall()]
        assert len(catalog_rows) == 2
        for r in catalog_rows:
            assert r["original_filename"] in ("IMG_0001.JPG", "IMG_0002.JPG")
            assert r["destination_filename"] is not None
            assert r["target_relative_path"] is not None
            assert "TEST" in r["destination_filename"]

