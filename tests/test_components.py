"""
Tests for PySide6 GUI Components (app/components/).
"""
import os
import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from app.components.drive_selector import DriveSelectorWidget
from app.components.progress_panel import ProgressPanelWidget
from app.components.log_console import LogConsoleWidget
from app.components.alert_banner import AlertBannerWidget


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app


def test_drive_selector_widget():
    widget = DriveSelectorWidget()
    assert widget is not None
    widget.refresh_drives()
    options = widget.get_selected_options()
    assert "dcim" in options
    assert "private" in options


def test_progress_panel_widget():
    panel = ProgressPanelWidget()
    panel.reset_progress()
    panel.update_overall(50, 100, "50 / 100 files")
    assert panel.overall_bar.value() == 50
    panel.update_file_progress(75, "Copying IMG_0001.JPG")
    assert panel.file_bar.value() == 75


def test_log_console_widget():
    console = LogConsoleWidget()
    console.add_duplicate("IMG_0001.JPG", "sha256hash123", 1024000)
    console.append_trace("[FASTCOPY] Copying files...")
    assert console.duplicate_table.rowCount() == 1
    assert "FASTCOPY" in console.trace_edit.toPlainText()


def test_alert_banner_widget():
    banner = AlertBannerWidget()
    banner.show_alert("Read error on card sector 45", level="WARNING")
    assert banner.isVisible()
    assert "sector 45" in banner.message_label.text()
    banner.dismiss()
    assert not banner.isVisible()
