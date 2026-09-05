"""
Tests for Multi-Layer Media File Filter & Configurable Extension Management (utils/media_filter.py).
"""
import pytest
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication
from utils.media_filter import (
    is_media_file, is_blacklisted_system_file,
    get_active_media_extensions, set_active_media_extensions,
    add_media_extension, remove_media_extension, reset_default_media_extensions,
    normalize_extension
)

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app

@pytest.fixture(autouse=True)
def reset_extensions_after_test():
    yield
    reset_default_media_extensions()


def test_blacklisted_system_files():
    assert is_blacklisted_system_file("IndexerVolumeGuid") is True
    assert is_blacklisted_system_file("WPSettings.dat") is True
    assert is_blacklisted_system_file("SONYCARD.IND") is True
    assert is_blacklisted_system_file("PP-101.db") is True
    assert is_blacklisted_system_file("INDEX.BDM") is True
    assert is_blacklisted_system_file("desktop.ini") is True
    assert is_blacklisted_system_file("thumbs.db") is True
    assert is_blacklisted_system_file("IMG_0001.JPG") is False


def test_media_file_filter_whitelist():
    assert is_media_file("DCIM/100EOS/IMG_0001.JPG") is True
    assert is_media_file("DCIM/100EOS/IMG_0001.CR3") is True
    assert is_media_file("DCIM/100EOS/CLIP_001.MP4") is True
    assert is_media_file("DCIM/100EOS/CLIP_001.MOV") is True
    assert is_media_file("PRIVATE/VOICE/AUDIO_001.WAV") is True
    assert is_media_file("INSTA360_001.INSP") is True
    assert is_media_file("INSTA360_001.INSV") is True
    assert is_media_file("BLACKMAGIC_001.BRAW") is True


def test_media_file_filter_sidecars():
    assert is_media_file("DCIM/100EOS/GOPRO_001.THM") is True
    assert is_media_file("DCIM/100EOS/GOPRO_001.LRF") is True
    assert is_media_file("DCIM/100EOS/PHOTO.XMP") is True


def test_media_file_filter_system_rejection():
    assert is_media_file("IndexerVolumeGuid") is False
    assert is_media_file("WPSettings.dat") is False
    assert is_media_file("SONYCARD.IND") is False
    assert is_media_file("PP-101.db") is False
    assert is_media_file("INDEX.BDM") is False
    assert is_media_file("AVIN0001.BNP") is False
    assert is_media_file("00011.CPI") is False


def test_files_with_no_extension_rejected():
    assert is_media_file("DSC00123") is False
    assert is_media_file("DCIM/100EOS/IMG_0001") is False
    assert is_media_file("random_unknown_file") is False
    assert is_media_file("DCIM/file_without_ext") is False
    assert is_media_file(".hidden_file") is False


def test_lightroom_catalogs_and_caches_rejected():
    assert is_media_file("Lightroom Catalog.lrcat") is False
    assert is_media_file("Previews.lrdata") is False
    assert is_media_file("Lightroom Catalog-v12.lrcat-data") is False
    assert is_media_file("Catalog.lrcat-lock") is False
    assert is_media_file("Catalog.lrcat-journal") is False
    assert is_media_file("Cache.bridgecache") is False


def test_documents_and_code_rejected():
    assert is_media_file("Notes.txt") is False
    assert is_media_file("export.csv") is False
    assert is_media_file("data.json") is False
    assert is_media_file("config.xml") is False
    assert is_media_file("document.pdf") is False
    assert is_media_file("program.exe") is False
    assert is_media_file("script.py") is False


def test_dynamic_add_and_remove_media_extension():
    assert is_media_file("drone_recording.customext") is False
    
    # 1. Add custom extension
    added = add_media_extension(".customext")
    assert added is True
    assert is_media_file("drone_recording.customext") is True
    assert is_media_file("drone_recording.CUSTOMEXT") is True

    # 2. Remove custom extension
    removed = remove_media_extension(".customext")
    assert removed is True
    assert is_media_file("drone_recording.customext") is False


def test_normalize_extension():
    assert normalize_extension("jpg") == ".jpg"
    assert normalize_extension(".JPG") == ".jpg"
    assert normalize_extension(" .PNG ") == ".png"
    assert normalize_extension("") == ""


def test_media_extension_filter_dialog(qapp, tmp_path):
    from app.components.extension_filter_dialog import MediaExtensionFilterDialog
    cfg_file = tmp_path / "test_config.json"
    dialog = MediaExtensionFilterDialog(config_path=str(cfg_file))
    
    assert dialog is not None
    assert "Media File Extension Filter" in dialog.windowTitle()
    assert ".jpg" in dialog.working_extensions
    
    # Add custom extension in dialog
    dialog.new_ext_input.setText(".myformat")
    dialog._on_add_custom_extension()
    assert ".myformat" in dialog.working_extensions
    
    dialog._on_save_and_apply()
    assert is_media_file("test.myformat") is True
