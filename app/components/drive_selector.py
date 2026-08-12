"""
Drive Selector Component for SD-FastBackup.
Provides drive selection QComboBox, refresh drive button, target directory selection, and folder options.
"""
import os
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QLineEdit, QCheckBox, QFileDialog
)
from PySide6.QtCore import Signal
from utils.drive_detector import get_available_drives


class DriveSelectorWidget(QGroupBox):
    """Widget for selecting source SD card drive, target backup directory, and options."""

    drive_changed = Signal(str)
    target_changed = Signal(str)
    options_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("SOURCE DRIVE & DESTINATION SETUP", parent)
        self._init_ui()
        self.refresh_drives()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 1. Drive Selection Row
        drive_layout = QHBoxLayout()
        drive_label = QLabel("Source Drive:")
        drive_label.setFixedWidth(110)
        self.drive_combo = QComboBox()
        self.drive_combo.setMinimumWidth(300)
        self.refresh_btn = QPushButton("Refresh Drives")
        self.refresh_btn.setFixedWidth(130)
        self.refresh_btn.clicked.connect(self.refresh_drives)

        drive_layout.addWidget(drive_label)
        drive_layout.addWidget(self.drive_combo, 1)
        drive_layout.addWidget(self.refresh_btn)
        main_layout.addLayout(drive_layout)

        # 2. Target Directory Row
        target_layout = QHBoxLayout()
        target_label = QLabel("Backup Target:")
        target_label.setFixedWidth(110)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Select target destination folder...")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setFixedWidth(130)
        self.browse_btn.clicked.connect(self._browse_target_folder)

        target_layout.addWidget(target_label)
        target_layout.addWidget(self.target_input, 1)
        target_layout.addWidget(self.browse_btn)
        main_layout.addLayout(target_layout)

        # 3. Custom Suffix & Subfolder Options Row
        opts_layout = QHBoxLayout()
        
        suffix_label = QLabel("Custom Suffix:")
        suffix_label.setFixedWidth(110)
        self.suffix_input = QLineEdit()
        self.suffix_input.setPlaceholderText("e.g. CAM_A or ROLL1 (Optional)")
        opts_layout.addWidget(suffix_label)
        opts_layout.addWidget(self.suffix_input, 1)

        opts_layout.addSpacing(20)

        self.dcim_cb = QCheckBox("DCIM/")
        self.dcim_cb.setChecked(True)
        self.private_cb = QCheckBox("PRIVATE/")
        self.private_cb.setChecked(True)
        self.full_vol_cb = QCheckBox("Full Volume Root")
        self.full_vol_cb.setChecked(False)

        self.dcim_cb.stateChanged.connect(self._on_options_changed)
        self.private_cb.stateChanged.connect(self._on_options_changed)
        self.full_vol_cb.stateChanged.connect(self._on_full_vol_changed)

        opts_layout.addWidget(self.dcim_cb)
        opts_layout.addWidget(self.private_cb)
        opts_layout.addWidget(self.full_vol_cb)

        main_layout.addLayout(opts_layout)

    def refresh_drives(self):
        """Enumerates connected drives and updates QComboBox."""
        self.drive_combo.clear()
        drives = get_available_drives()

        if not drives:
            self.drive_combo.addItem("No removable drives detected", "")
            return

        for d in drives:
            free_gb = d["free_bytes"] / (1024 ** 3)
            total_gb = d["total_bytes"] / (1024 ** 3)
            display_str = f"{d['path']} [{d['label']}] - {d['drive_type']} ({free_gb:.1f} GB free of {total_gb:.1f} GB)"
            self.drive_combo.addItem(display_str, d["path"])

    def _browse_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Target Directory")
        if folder:
            self.target_input.setText(folder)
            self.target_changed.emit(folder)

    def _on_full_vol_changed(self, state):
        if self.full_vol_cb.isChecked():
            self.dcim_cb.setEnabled(False)
            self.private_cb.setEnabled(False)
        else:
            self.dcim_cb.setEnabled(True)
            self.private_cb.setEnabled(True)
        self._on_options_changed()

    def _on_options_changed(self):
        self.options_changed.emit(self.get_selected_options())

    def get_selected_drive_path(self) -> str:
        return self.drive_combo.currentData() or ""

    def get_target_directory(self) -> str:
        return self.target_input.text().strip()

    def get_custom_suffix(self) -> str:
        return self.suffix_input.text().strip()

    def get_selected_options(self) -> dict:
        return {
            "dcim": self.dcim_cb.isChecked(),
            "private": self.private_cb.isChecked(),
            "full_volume": self.full_vol_cb.isChecked()
        }
