"""
Drive & Source Device Selector Component for SD-FastBackup.
Allows selecting source drive letters (E:\\, F:\\), connected MTP Mobile Phones (Pixel 8 Pro, iPhone),
browsing custom folders, target backup directory, and options.
"""
import os
from PySide6.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QLineEdit, QCheckBox, QFileDialog
)
from PySide6.QtCore import Signal, QThread
from utils.drive_detector import get_available_drives, is_same_drive
from app.components.flow_layout import FlowLayout
from utils.path_formatter import normalize_win_path
from core.mtp_engine import is_mtp_path, browse_with_windows_shell


class DriveDetectorWorker(QThread):
    """Background worker to enumerate drives & MTP devices without freezing the GUI."""
    drives_detected = Signal(list)

    def run(self):
        try:
            drives = get_available_drives()
        except Exception:
            drives = []
        self.drives_detected.emit(drives)


class DriveSelectorWidget(QGroupBox):
    """Widget for selecting source drive / MTP phone device or custom folder, target backup directory, and options."""

    drive_changed = Signal(str)
    target_changed = Signal(str)
    options_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("SOURCE SELECTION (SD CARDS & MOBILE PHONES) & DESTINATION SETUP", parent)
        self._detector_worker: Optional[DriveDetectorWorker] = None
        self._init_ui()
        self.refresh_drives(blocking=False)

    def stop_threads(self):
        """Safely stops any background detector thread before destruction."""
        if self._detector_worker and self._detector_worker.isRunning():
            self._detector_worker.quit()
            self._detector_worker.wait(1000)

    def closeEvent(self, event):
        self.stop_threads()
        super().closeEvent(event)

    def __del__(self):
        try:
            self.stop_threads()
        except Exception:
            pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)

        # 1. Source Drive / Phone Selection Row
        drive_layout = QHBoxLayout()
        drive_label = QLabel("Source Device/Path:")
        drive_label.setMinimumWidth(120)
        
        self.drive_combo = QComboBox()
        self.drive_combo.setEditable(True)
        self.drive_combo.setMinimumWidth(300)
        # Drive entries carry long labels ("D:\\ [SDCARD] - Removable (12.3 GB free of
        # 32.0 GB)"). Without this the widest entry sets the widget's minimum width and
        # drags the whole window's minimum out with it.
        self.drive_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.drive_combo.setMinimumContentsLength(20)
        self.drive_combo.currentTextChanged.connect(self._on_paths_updated)
        
        self.refresh_btn = QPushButton("Refresh Devices")
        self.refresh_btn.clicked.connect(lambda: self.refresh_drives(blocking=False))

        self.browse_src_btn = QPushButton("Browse Folder...")
        self.browse_src_btn.clicked.connect(self._browse_source_folder)

        drive_layout.addWidget(drive_label)
        drive_layout.addWidget(self.drive_combo, 1)
        drive_layout.addWidget(self.refresh_btn)
        drive_layout.addWidget(self.browse_src_btn)
        main_layout.addLayout(drive_layout)

        # 2. Target Directory Row
        target_layout = QHBoxLayout()
        target_label = QLabel("Backup Target:")
        target_label.setMinimumWidth(120)
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Select target destination folder...")
        self.target_input.textChanged.connect(self._on_paths_updated)
        
        self.browse_btn = QPushButton("Browse Target...")
        self.browse_btn.clicked.connect(self._browse_target_folder)

        target_layout.addWidget(target_label)
        target_layout.addWidget(self.target_input, 1)
        target_layout.addWidget(self.browse_btn)
        main_layout.addLayout(target_layout)

        # 3. Custom Suffix & Subfolder Options Row
        opts_layout = QHBoxLayout()
        
        suffix_label = QLabel("Custom Suffix:")
        suffix_label.setMinimumWidth(120)
        self.suffix_input = QLineEdit()
        self.suffix_input.setPlaceholderText("e.g. MAVIC or PIXEL8 (Optional)")
        opts_layout.addWidget(suffix_label)
        opts_layout.addWidget(self.suffix_input, 1)

        main_layout.addLayout(opts_layout)

        # 3b. Toggle row - a FlowLayout so long labels wrap instead of being clipped
        toggles_layout = FlowLayout(margin=0, h_spacing=14, v_spacing=6)

        self.dcim_cb = QCheckBox("DCIM/")
        self.dcim_cb.setChecked(True)
        self.private_cb = QCheckBox("PRIVATE/")
        self.private_cb.setChecked(True)
        self.full_vol_cb = QCheckBox("Full Storage")
        self.full_vol_cb.setChecked(False)

        self.move_cb = QCheckBox("🚚 Move files (Instant organize)")
        self.move_cb.setChecked(False)
        self.move_cb.setEnabled(False)
        self.move_cb.setToolTip("Move mode is only available when source and target are on the same local drive.")

        self.rescan_cb = QCheckBox("🔄 Reconcile & rescan destination on finish")
        self.rescan_cb.setChecked(False)
        self.rescan_cb.setToolTip(
            "After the backup, re-scan the destination date folders just written to, index any "
            "files that were added outside this app, and backfill missing metadata."
        )

        self.dcim_cb.stateChanged.connect(self._on_options_changed)
        self.private_cb.stateChanged.connect(self._on_options_changed)
        self.full_vol_cb.stateChanged.connect(self._on_full_vol_changed)
        self.move_cb.stateChanged.connect(self._on_options_changed)

        self.btn_ext_filter = QPushButton("⚙️ Extension Filter...")
        self.btn_ext_filter.setToolTip("Configure allowed photo/video/audio extensions and add custom formats")
        self.btn_ext_filter.clicked.connect(self._open_extension_filter_dialog)

        toggles_layout.addWidget(self.dcim_cb)
        toggles_layout.addWidget(self.private_cb)
        toggles_layout.addWidget(self.full_vol_cb)
        toggles_layout.addWidget(self.move_cb)
        toggles_layout.addWidget(self.rescan_cb)
        toggles_layout.addWidget(self.btn_ext_filter)

        main_layout.addLayout(toggles_layout)

        # 4. Indicator Banner
        self.same_drive_info = QLabel("⚡ Same drive detected: Instant 0-byte Move Mode available.")
        self.same_drive_info.setWordWrap(True)
        self.same_drive_info.setStyleSheet("color: #00FFF5; font-size: 11px; font-weight: bold; margin-left: 125px;")
        self.same_drive_info.hide()
        main_layout.addWidget(self.same_drive_info)

    def refresh_drives(self, blocking: bool = False):
        """Enumerates connected drive letters and MTP phone devices asynchronously."""
        if blocking:
            drives = get_available_drives()
            self._on_drives_detected(drives)
            return

        if self._detector_worker and self._detector_worker.isRunning():
            return

        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ Scanning...")
        
        if self.drive_combo.count() == 0:
            self.drive_combo.addItem("⏳ Scanning connected drives & mobile devices...", "")

        self._detector_worker = DriveDetectorWorker(self)
        self._detector_worker.drives_detected.connect(self._on_drives_detected)
        self._detector_worker.start()

    def _on_drives_detected(self, drives: list):
        """Callback invoked when background drive detection completes."""
        current_text = self.get_selected_drive_path()
        self.drive_combo.clear()

        if not drives:
            self.drive_combo.addItem("No removable drives or MTP devices detected", "")
        else:
            for d in drives:
                raw_p = d["path"]
                if is_mtp_path(raw_p):
                    display_str = f"📱 {d['label']} [{d['drive_type']}]"
                    self.drive_combo.addItem(display_str, raw_p)
                else:
                    norm_p = normalize_win_path(raw_p)
                    free_gb = d["free_bytes"] / (1024 ** 3)
                    total_gb = d["total_bytes"] / (1024 ** 3)
                    display_str = f"💾 {norm_p} [{d['label']}] - {d['drive_type']} ({free_gb:.1f} GB free of {total_gb:.1f} GB)"
                    self.drive_combo.addItem(display_str, norm_p)

        if current_text:
            self.set_selected_source_path(current_text)

        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("Refresh Devices")
        self.update_move_mode_availability()

    def _browse_source_folder(self):
        """Launches Windows Shell BrowseForFolder dialog supporting both local drives & MTP phones."""
        hwnd = int(self.winId()) if self.winId() else 0
        shell_path = browse_with_windows_shell(hwnd)
        if shell_path:
            self.set_selected_source_path(shell_path)
            self.drive_changed.emit(shell_path)
            return

        # Fallback Qt QFileDialog
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

    def _open_extension_filter_dialog(self):
        """Opens the Media Extension Filter configuration dialog."""
        from app.components.extension_filter_dialog import MediaExtensionFilterDialog
        dialog = MediaExtensionFilterDialog(parent=self)
        dialog.exec()

    def _on_paths_updated(self):
        self.update_move_mode_availability()

    def update_move_mode_availability(self):
        """Auto-detects if source and target share the same drive volume."""
        src = self.get_selected_drive_path()
        tgt = self.get_target_directory()

        if src and tgt and not is_mtp_path(src) and is_same_drive(src, tgt):
            self.move_cb.setEnabled(True)
            self.move_cb.setToolTip("Instant same-drive file pointer organization (0-byte move). Original file is moved.")
            if not self.move_cb.property("user_toggled"):
                self.move_cb.setChecked(True)
            self.same_drive_info.show()
        else:
            self.move_cb.setEnabled(False)
            self.move_cb.setChecked(False)
            self.move_cb.setToolTip("Move mode is only available when source and target are on the same local drive.")
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
        if not path_str:
            return
        
        if is_mtp_path(path_str):
            norm_p = path_str
        else:
            norm_p = normalize_win_path(path_str)

        for i in range(self.drive_combo.count()):
            if self.drive_combo.itemData(i) == norm_p or self.drive_combo.itemText(i) == norm_p:
                self.drive_combo.setCurrentIndex(i)
                self.update_move_mode_availability()
                return
        
        prefix = "📱 " if is_mtp_path(norm_p) else "📁 "
        self.drive_combo.addItem(f"{prefix}{norm_p}", norm_p)
        self.drive_combo.setCurrentIndex(self.drive_combo.count() - 1)
        self.update_move_mode_availability()

    def get_selected_drive_path(self) -> str:
        data = self.drive_combo.currentData()
        if data:
            return data if is_mtp_path(data) else normalize_win_path(data)
        text = self.drive_combo.currentText().replace("📁 ", "").replace("📱 ", "").replace("💾 ", "").strip()
        return text if is_mtp_path(text) else normalize_win_path(text)

    def get_target_directory(self) -> str:
        return normalize_win_path(self.target_input.text().strip())

    def get_custom_suffix(self) -> str:
        return self.suffix_input.text().strip()

    def get_is_move_mode(self) -> bool:
        return self.move_cb.isEnabled() and self.move_cb.isChecked()

    def get_auto_rescan(self) -> bool:
        return self.rescan_cb.isChecked()

    def get_selected_options(self) -> dict:
        return {
            "dcim": self.dcim_cb.isChecked(),
            "private": self.private_cb.isChecked(),
            "full_volume": self.full_vol_cb.isChecked(),
            "move_mode": self.get_is_move_mode()
        }
