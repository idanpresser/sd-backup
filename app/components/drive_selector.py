"""
Drive & Source Folder Selector Component for SD-FastBackup.
Allows selecting source drive or browsing custom source folder, target backup directory, options,
and Same-Drive instant Move Mode auto-detection.
"""
import os
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QLineEdit, QCheckBox, QFileDialog
)
from PySide6.QtCore import Signal
from utils.drive_detector import get_available_drives, is_same_drive
from utils.path_formatter import normalize_win_path


class DriveSelectorWidget(QGroupBox):
    """Widget for selecting source drive or custom folder, target backup directory, and options."""

    drive_changed = Signal(str)
    target_changed = Signal(str)
    options_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("SOURCE SELECTION & DESTINATION SETUP", parent)
        self._init_ui()
        self.refresh_drives()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 1. Source Drive / Folder Selection Row
        drive_layout = QHBoxLayout()
        drive_label = QLabel("Source Location:")
        drive_label.setFixedWidth(110)
        
        self.drive_combo = QComboBox()
        self.drive_combo.setEditable(True)
        self.drive_combo.setMinimumWidth(280)
        self.drive_combo.currentTextChanged.connect(self._on_paths_updated)
        
        self.refresh_btn = QPushButton("Refresh Drives")
        self.refresh_btn.setFixedWidth(110)
        self.refresh_btn.clicked.connect(self.refresh_drives)

        self.browse_src_btn = QPushButton("Browse Source...")
        self.browse_src_btn.setFixedWidth(120)
        self.browse_src_btn.clicked.connect(self._browse_source_folder)

        drive_layout.addWidget(drive_label)
        drive_layout.addWidget(self.drive_combo, 1)
        drive_layout.addWidget(self.refresh_btn)
        drive_layout.addWidget(self.browse_src_btn)
        main_layout.addLayout(drive_layout)

        # 2. Target Directory Row
        target_layout = QHBoxLayout()
        target_label = QLabel("Backup Target:")
        target_label.setFixedWidth(110)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Select target destination folder...")
        self.target_input.textChanged.connect(self._on_paths_updated)
        
        self.browse_btn = QPushButton("Browse Target...")
        self.browse_btn.setFixedWidth(120)
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

        opts_layout.addSpacing(15)

        self.dcim_cb = QCheckBox("DCIM/")
        self.dcim_cb.setChecked(True)
        self.private_cb = QCheckBox("PRIVATE/")
        self.private_cb.setChecked(True)
        self.full_vol_cb = QCheckBox("Full Folder / Volume")
        self.full_vol_cb.setChecked(False)

        self.move_cb = QCheckBox("🚚 Move files (Instant organize)")
        self.move_cb.setChecked(False)
        self.move_cb.setEnabled(False)
        self.move_cb.setToolTip("Move mode is only available when source and target are on the same drive.")

        self.dcim_cb.stateChanged.connect(self._on_options_changed)
        self.private_cb.stateChanged.connect(self._on_options_changed)
        self.full_vol_cb.stateChanged.connect(self._on_full_vol_changed)
        self.move_cb.stateChanged.connect(self._on_options_changed)

        opts_layout.addWidget(self.dcim_cb)
        opts_layout.addWidget(self.private_cb)
        opts_layout.addWidget(self.full_vol_cb)
        opts_layout.addWidget(self.move_cb)

        main_layout.addLayout(opts_layout)

        # 4. Same Drive Status Indicator Banner
        self.same_drive_info = QLabel("⚡ Same drive detected: Instant 0-byte Move Mode available.")
        self.same_drive_info.setStyleSheet("color: #00FFF5; font-size: 11px; font-weight: bold; margin-left: 115px;")
        self.same_drive_info.hide()
        main_layout.addWidget(self.same_drive_info)

    def refresh_drives(self):
        """Enumerates connected drives and updates QComboBox."""
        current_text = self.get_selected_drive_path()
        self.drive_combo.clear()
        drives = get_available_drives()

        if not drives:
            self.drive_combo.addItem("No removable drives detected", "")
        else:
            for d in drives:
                norm_p = normalize_win_path(d["path"])
                free_gb = d["free_bytes"] / (1024 ** 3)
                total_gb = d["total_bytes"] / (1024 ** 3)
                display_str = f"{norm_p} [{d['label']}] - {d['drive_type']} ({free_gb:.1f} GB free of {total_gb:.1f} GB)"
                self.drive_combo.addItem(display_str, norm_p)

        if current_text:
            self.set_selected_source_path(current_text)

        self.update_move_mode_availability()

    def _browse_source_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Directory / SD Folder")
        if folder:
            norm_f = normalize_win_path(folder)
            self.set_selected_source_path(norm_f)
            self.drive_changed.emit(norm_f)

    def _browse_target_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Target Directory")
        if folder:
            norm_f = normalize_win_path(folder)
            self.target_input.setText(norm_f)
            self.target_changed.emit(norm_f)

    def _on_paths_updated(self):
        self.update_move_mode_availability()

    def update_move_mode_availability(self):
        """Auto-detects if source and target share the same drive volume."""
        src = self.get_selected_drive_path()
        tgt = self.get_target_directory()

        if src and tgt and is_same_drive(src, tgt):
            self.move_cb.setEnabled(True)
            self.move_cb.setToolTip("Instant same-drive file pointer organization (0-byte move). Original file is moved.")
            if not self.move_cb.property("user_toggled"):
                self.move_cb.setChecked(True)
            self.same_drive_info.show()
        else:
            self.move_cb.setEnabled(False)
            self.move_cb.setChecked(False)
            self.move_cb.setToolTip("Move mode is only available when source and destination are on the same drive.")
            self.same_drive_info.hide()

    def _on_full_vol_changed(self, state):
        if self.full_vol_cb.isChecked():
            self.dcim_cb.setEnabled(False)
            self.private_cb.setEnabled(False)
        else:
            self.dcim_cb.setEnabled(True)
            self.private_cb.setEnabled(True)
        self._on_options_changed()

    def _on_options_changed(self):
        if self.sender() == self.move_cb:
            self.move_cb.setProperty("user_toggled", True)
        self.options_changed.emit(self.get_selected_options())

    def set_selected_source_path(self, path_str: str):
        """Sets source path in combo box."""
        if not path_str:
            return
        norm_p = normalize_win_path(path_str)
        for i in range(self.drive_combo.count()):
            if self.drive_combo.itemData(i) == norm_p or self.drive_combo.itemText(i) == norm_p:
                self.drive_combo.setCurrentIndex(i)
                self.update_move_mode_availability()
                return
        self.drive_combo.addItem(f"📁 {norm_p}", norm_p)
        self.drive_combo.setCurrentIndex(self.drive_combo.count() - 1)
        self.update_move_mode_availability()

    def get_selected_drive_path(self) -> str:
        data = self.drive_combo.currentData()
        if data:
            return normalize_win_path(data)
        text = self.drive_combo.currentText().replace("📁 ", "").strip()
        return normalize_win_path(text)

    def get_target_directory(self) -> str:
        return normalize_win_path(self.target_input.text().strip())

    def get_custom_suffix(self) -> str:
        return self.suffix_input.text().strip()

    def get_is_move_mode(self) -> bool:
        return self.move_cb.isEnabled() and self.move_cb.isChecked()

    def get_selected_options(self) -> dict:
        return {
            "dcim": self.dcim_cb.isChecked(),
            "private": self.private_cb.isChecked(),
            "full_volume": self.full_vol_cb.isChecked(),
            "move_mode": self.get_is_move_mode()
        }
