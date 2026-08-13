"""
Tests for PySide6 Database Catalog Viewer GUI & Sync Dialog (app/components/db_viewer.py).
"""
import os
import sys
import tempfile
import shutil
import pytest

from PySide6.QtWidgets import QApplication
from app.components.db_viewer import DBCatalogDialog, DBSyncDialog
from core.db import DatabaseManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def sample_db_env(tmp_path):
    root_dir = str(tmp_path / "gui_db_target")
    os.makedirs(root_dir, exist_ok=True)
    db = DatabaseManager(root_dir)

    hash_val = "gui_test_hash_1"
    db.register_file(hash_val, "PHOTO_01.JPG", "DCIM/PHOTO_01.JPG", 2048000, "2026-08-13T10:00:00", "EXIF")
    db.update_transfer_status(hash_val, "E:/DCIM/PHOTO_01.JPG", os.path.join(root_dir, "PHOTO_01.JPG"), "COPIED")
    db.register_metadata(hash_val, "PHOTO_01.JPG", {
        "camera_make": "Canon",
        "camera_model": "EOS R5",
        "lens_model": "RF 50mm F1.2L",
        "iso": 100,
        "aperture": "f/1.2",
        "shutter_speed": "1/1000",
        "raw_json": '{"Image Make": "Canon"}'
    })
    db.checkpoint()
    return root_dir, db


def test_db_catalog_dialog_creation_and_load(qapp, sample_db_env):
    root_dir, db = sample_db_env
    dialog = DBCatalogDialog(target_dir=root_dir)

    assert dialog is not None
    assert dialog.windowTitle() == "Database Catalog Manager"
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 1).text() == "PHOTO_01.JPG"


def test_db_catalog_dialog_filter(qapp, sample_db_env):
    root_dir, db = sample_db_env
    dialog = DBCatalogDialog(target_dir=root_dir)

    # Filter with non-matching text
    dialog.search_input.setText("NON_EXISTENT_FILE")
    dialog._apply_filter()
    assert dialog.table.isRowHidden(0) is True

    # Clear filter
    dialog.search_input.setText("PHOTO")
    dialog._apply_filter()
    assert dialog.table.isRowHidden(0) is False


def test_db_sync_dialog_preview(qapp, sample_db_env):
    root_dir, db = sample_db_env
    sync_dialog = DBSyncDialog(target_dir=root_dir)

    assert sync_dialog is not None
    assert "Database & Disk Synchronization" in sync_dialog.windowTitle()
