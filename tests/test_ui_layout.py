"""
Tests for responsive layout and window sizing (app/).

Two measured defects motivated these:
  (a) drive_selector pinned three buttons to setFixedWidth(115) while their labels
      need 188-224px with the QSS padding, so they clipped at EVERY window size.
  (b) The options row required 2023px of natural width while main_window declared
      setMinimumSize(880, 680) - below the window's own 1883px minimumSizeHint - so
      Qt was allowed into a geometry the layout could not honour.
"""
import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton, QCheckBox

from app.components.drive_selector import DriveSelectorWidget
from app.components.progress_panel import ProgressPanelWidget
from app.main_window import MainWindow


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["--platform", "offscreen"])
    yield app


# --- (a) no permanently-clipped controls ------------------------------------

def test_source_and_target_buttons_are_not_pinned_below_their_labels():
    widget = DriveSelectorWidget()
    for btn in (widget.refresh_btn, widget.browse_src_btn, widget.browse_btn):
        needed = btn.sizeHint().width()
        assert btn.maximumWidth() >= needed, (
            f"{btn.text()!r} is capped at {btn.maximumWidth()}px but needs {needed}px"
        )


def test_no_control_is_clipped_at_a_normal_window_size(qapp):
    window = MainWindow(config_path=os.devnull + ".json")
    window.resize(1100, 800)
    window.show()
    qapp.processEvents()

    clipped = []
    for cls in (QPushButton, QCheckBox):
        for w in window.findChildren(cls):
            if not w.isVisibleTo(window):
                continue
            if w.width() < w.minimumSizeHint().width():
                clipped.append((w.text(), w.width(), w.minimumSizeHint().width()))

    assert not clipped, f"clipped controls at 1100x800: {clipped}"


# --- (b) the window minimum must be one the layout can honour ---------------

def test_options_row_can_wrap_into_a_narrow_window():
    widget = DriveSelectorWidget()
    minimum = widget.layout().totalMinimumSize().width()
    assert minimum <= 900, (
        f"drive selector demands {minimum}px minimum; it must wrap to fit a ~880px window"
    )


def test_window_minimum_is_not_below_what_its_layout_requires():
    """An explicit floor under the layout's own minimum lets Qt clip its children."""
    window = MainWindow(config_path=os.devnull + ".json")
    required = window.minimumSizeHint().width()
    declared = window.minimumWidth()
    assert declared == 0 or declared >= required, (
        f"window minimum width {declared}px is below the layout's own {required}px requirement"
    )


def test_layout_minimum_fits_a_normal_screen():
    """The layout demanded 1883px before wrapping; it must fit a common display."""
    window = MainWindow(config_path=os.devnull + ".json")
    required = window.minimumSizeHint().width()
    assert required <= 1280, f"window cannot shrink below {required}px; it must fit a 1280px screen"


def test_window_opens_maximized():
    window = MainWindow(config_path=os.devnull + ".json")
    window.show_default()
    assert window.windowState() & Qt.WindowMaximized


# --- the removed 'Current File' progress bar --------------------------------

def test_progress_panel_has_no_current_file_bar():
    panel = ProgressPanelWidget()
    assert not hasattr(panel, "file_bar"), (
        "the Current File bar duplicated overall progress or sat pinned at 100%; it was removed"
    )
    assert not hasattr(panel, "update_file_progress")


def test_progress_panel_still_reports_overall_and_transfer_progress():
    panel = ProgressPanelWidget()
    panel.reset_progress()
    panel.update_overall(50, 100, "50 / 100 files")
    assert panel.overall_bar.value() == 50

    panel.reset_for_transfer(10, 1024.0)
    panel.update_transfer_progress(5, 10, "IMG_0005.JPG")
    assert panel.overall_bar.value() == 50
    assert "IMG_0005.JPG" in panel.status_label.text()
