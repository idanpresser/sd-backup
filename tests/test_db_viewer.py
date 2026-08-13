"""
Tests for PySide6 Database Catalog Viewer GUI & Sync Dialog (app/components/db_viewer.py).
"""
import os
import sys
import tempfile
import shutil
import pytest

from PySide6.QtWidgets import QApplication
from app.components.db_viewer import DBCatalogWidget, DBSyncDialog
from app.main_window import MainWindow
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


def test_db_catalog_widget_creation_and_load(qapp, sample_db_env):
    root_dir, db = sample_db_env
    widget = DBCatalogWidget(target_dir=root_dir)

    assert widget is not None
    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 1).text() == "PHOTO_01.JPG"


def test_db_catalog_widget_filter(qapp, sample_db_env):
    root_dir, db = sample_db_env
    widget = DBCatalogWidget(target_dir=root_dir)

    # Filter with non-matching text
    widget.search_input.setText("NON_EXISTENT_FILE")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is True

    # Clear filter
    widget.search_input.setText("PHOTO")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is False


def test_db_sync_dialog_preview(qapp, sample_db_env):
    root_dir, db = sample_db_env
    sync_dialog = DBSyncDialog(target_dir=root_dir)

    assert sync_dialog is not None
    assert "Database & Disk Synchronization" in sync_dialog.windowTitle()


def test_main_window_tab_widget(qapp, sample_db_env):
    root_dir, db = sample_db_env
    window = MainWindow()
    assert hasattr(window, "tab_widget")
    assert window.tab_widget.count() == 2
    assert window.tab_widget.tabText(0) == "⚡ Backup Launcher"
    assert window.tab_widget.tabText(1) == "🗃️ Database Catalog"


def test_suffix_renamer_dialog(qapp, sample_db_env):
    root_dir, db = sample_db_env
    from app.components.db_viewer import SuffixRenamerDialog
    dialog = SuffixRenamerDialog(target_dir=root_dir)

    assert dialog is not None
    assert "Batch Suffix Renamer" in dialog.windowTitle()


def test_search_timer_debouncing(qapp, sample_db_env):
    root_dir, db = sample_db_env
    widget = DBCatalogWidget(target_dir=root_dir)

    assert hasattr(widget, "search_timer")
    assert widget.search_timer.interval() >= 300


def test_db_sync_dialog_uncataloged_options(qapp, sample_db_env):
    root_dir, db = sample_db_env
    sync_dialog = DBSyncDialog(target_dir=root_dir)

    assert hasattr(sync_dialog, "radio_add_uncataloged")
    assert hasattr(sync_dialog, "radio_delete_uncataloged")
    assert hasattr(sync_dialog, "radio_ignore_uncataloged")
    assert sync_dialog.radio_add_uncataloged.isChecked() is True


def test_db_catalog_widget_delete_buttons(qapp, sample_db_env):
    root_dir, db = sample_db_env
    widget = DBCatalogWidget(target_dir=root_dir)

    assert hasattr(widget, "btn_purge_db")
    assert hasattr(widget, "btn_delete_disk_db")


def test_case_invariant_and_wildcard_search(qapp, sample_db_env):
    root_dir, db = sample_db_env
    widget = DBCatalogWidget(target_dir=root_dir)

    # 1. Uppercase match (sample contains PHOTO_01.JPG and Canon EOS R5)
    widget.search_input.setText("CANON EOS")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is False

    # 2. Wildcard asterisk * match
    widget.search_input.setText("photo_*.jpg")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is False

    # 3. Wildcard question mark ? match
    widget.search_input.setText("photo_??.jpg")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is False

    # 4. Non-matching wildcard
    widget.search_input.setText("photo_???.jpg")
    widget._apply_filter()
    assert widget.table.isRowHidden(0) is True




