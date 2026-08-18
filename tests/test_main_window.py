"""
Tests for Primary QMainWindow (app/main_window.py).
"""
import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow

@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app

def test_main_window_initialization(tmp_path):
    cfg_file = tmp_path / "init_config.json"
    window = MainWindow(config_path=str(cfg_file))
    assert window is not None
    assert window.windowTitle() == "SD-FastBackup"
    assert window.drive_selector is not None
    assert window.progress_panel is not None
    assert window.log_console is not None
    assert window.alert_banner is not None

def test_config_save_and_load(tmp_path):
    cfg_file = tmp_path / "config.json"
    window = MainWindow(config_path=str(cfg_file))
    window.drive_selector.target_input.setText(str(tmp_path))
    window.save_config()
    
    assert os.path.exists(cfg_file)
    
    window_2 = MainWindow(config_path=str(cfg_file))
    assert window_2.drive_selector.get_target_directory() == str(tmp_path)
