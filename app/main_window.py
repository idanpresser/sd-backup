"""
Primary QMainWindow & Event Wiring for SD-FastBackup.
Assembles DriveSelectorWidget, ProgressPanelWidget, LogConsoleWidget, AlertBannerWidget,
and embedded Database Catalog Manager inside a Tabbed User Interface.
Handles configuration persistence and QThread worker lifecycle.
"""
import os
import json
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QMessageBox, QApplication, QTabWidget
)
from PySide6.QtCore import Qt

from app.components.drive_selector import DriveSelectorWidget
from app.components.progress_panel import ProgressPanelWidget
from app.components.log_console import LogConsoleWidget
from app.components.alert_banner import AlertBannerWidget
from app.components.db_viewer import DBCatalogWidget
from core.worker import BackupWorker
from core.logger import QtSignalingLogHandler
from core.mtp_engine import is_mtp_path
from utils.path_formatter import normalize_win_path


class MainWindow(QMainWindow):
    """Primary Application Window for SD-FastBackup with Tabbed Architecture."""

    def __init__(self, config_path: Optional[str] = None):
        super().__init__()
        self.setWindowTitle("SD-FastBackup")
        self.resize(1020, 800)
        self.setMinimumSize(880, 680)

        self.config_path = config_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
        self.worker: Optional[BackupWorker] = None
        self.fastcopy_path = ""
        self._rescan_full_drive = False

        self._init_ui()
        self._setup_logging()
        self.load_config()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 1. Header Banner
        header_layout = QHBoxLayout()
        title_label = QLabel("⚡ SD-FastBackup")
        title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ADB5;")
        subtitle_label = QLabel("Ultra-Fast Deduplicated SD Card & Mobile Phone (MTP) Backup Engine")
        subtitle_label.setStyleSheet("color: #888888; font-size: 12px; margin-left: 10px;")

        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label, 1)
        main_layout.addLayout(header_layout)

        # 2. Main Tabbed Layout
        self.tab_widget = QTabWidget(central_widget)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1E1E1E;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #2A2A2A;
                color: #AAAAAA;
                font-size: 13px;
                font-weight: bold;
                padding: 8px 22px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #00ADB5;
                color: #FFFFFF;
            }
            QTabBar::tab:hover:!selected {
                background-color: #383838;
                color: #00FFF5;
            }
        """)

        # --- TAB 1: Backup Engine ---
        launcher_tab = QWidget()
        launcher_layout = QVBoxLayout(launcher_tab)
        launcher_layout.setSpacing(10)
        launcher_layout.setContentsMargins(12, 12, 12, 12)

        self.alert_banner = AlertBannerWidget(launcher_tab)
        launcher_layout.addWidget(self.alert_banner)

        self.drive_selector = DriveSelectorWidget(launcher_tab)
        launcher_layout.addWidget(self.drive_selector)

        # Control Buttons Row
        action_layout = QHBoxLayout()

        self.start_btn = QPushButton("🚀 START BACKUP")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ADB5;
                color: #FFFFFF;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #00FFF5;
                color: #121212;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #666666;
            }
        """)
        self.start_btn.clicked.connect(self.start_backup)

        self.cancel_btn = QPushButton("⛔ CANCEL")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #5A1E1E;
                color: #FF8888;
                font-size: 14px;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #8B0000;
                color: #FFFFFF;
            }
            QPushButton:disabled {
                background-color: #222222;
                color: #555555;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_backup)

        action_layout.addWidget(self.start_btn, 3)
        action_layout.addWidget(self.cancel_btn, 1)
        launcher_layout.addLayout(action_layout)

        self.progress_panel = ProgressPanelWidget(launcher_tab)
        launcher_layout.addWidget(self.progress_panel)

        self.log_console = LogConsoleWidget(launcher_tab)
        launcher_layout.addWidget(self.log_console, 1)

        self.tab_widget.addTab(launcher_tab, "⚡ Backup Launcher")

        # --- TAB 2: Database Catalog Manager ---
        self.db_catalog_widget = DBCatalogWidget(target_dir="", parent=self)
        self.tab_widget.addTab(self.db_catalog_widget, "🗃️ Database Catalog")

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tab_widget, 1)

    def _on_tab_changed(self, index: int):
        """When switching to Database Catalog tab, auto-sync target directory and refresh catalog."""
        if index == 1:
            target_dir = self.drive_selector.get_target_directory()
            self.db_catalog_widget.set_target_dir(target_dir)

    def _setup_logging(self):
        """Routes Python logging output to System Trace Tab."""
        self.log_handler = QtSignalingLogHandler()
        self.log_handler.log_emitted.connect(self._on_log_emitted)
        logger = logging.getLogger()
        logger.addHandler(self.log_handler)
        logger.setLevel(logging.INFO)

    def _on_log_emitted(self, message: str, level: str):
        self.log_console.append_trace(f"[{level}] {message}")

    def load_config(self):
        """Loads preferences from config.json and populates UI fields."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    
                    src_p = cfg.get("source_path", "")
                    if src_p:
                        self.drive_selector.set_selected_source_path(src_p if is_mtp_path(src_p) else normalize_win_path(src_p))
                        
                    target_dir = cfg.get("target_directory", "")
                    if target_dir:
                        norm_target = normalize_win_path(target_dir)
                        self.drive_selector.target_input.setText(norm_target)
                        self.db_catalog_widget.set_target_dir(norm_target)
                        
                    suffix = cfg.get("custom_suffix", "")
                    if suffix:
                        self.drive_selector.suffix_input.setText(suffix)

                    self.fastcopy_path = cfg.get("fastcopy_path", "")

                    sub_opts = cfg.get("subfolder_options", {})
                    if "dcim" in sub_opts:
                        self.drive_selector.dcim_cb.setChecked(sub_opts["dcim"])
                    if "private" in sub_opts:
                        self.drive_selector.private_cb.setChecked(sub_opts["private"])
                    if "full_volume" in sub_opts:
                        self.drive_selector.full_vol_cb.setChecked(sub_opts["full_volume"])
                    if "move_mode" in sub_opts:
                        if self.drive_selector.move_cb.isEnabled():
                            self.drive_selector.move_cb.setChecked(sub_opts["move_mode"])

                    media_exts = cfg.get("media_extensions", [])
                    if media_exts:
                        from utils.media_filter import set_active_media_extensions
                        set_active_media_extensions(media_exts)

                    self.drive_selector.rescan_cb.setChecked(bool(cfg.get("auto_rescan_after_import", False)))
                    self._rescan_full_drive = bool(cfg.get("rescan_full_drive", False))

                    self.drive_selector.update_move_mode_availability()

            except Exception as e:
                logging.warning(f"Could not load config file: {e}")

    def save_config(self):
        """Saves current GUI preferences to config.json."""
        try:
            from utils.media_filter import get_active_media_extensions
            cfg = {
                "source_path": self.drive_selector.get_selected_drive_path(),
                "target_directory": self.drive_selector.get_target_directory(),
                "custom_suffix": self.drive_selector.get_custom_suffix(),
                "fastcopy_path": self.fastcopy_path,
                "media_extensions": sorted(list(get_active_media_extensions())),
                "subfolder_options": self.drive_selector.get_selected_options(),
                "auto_rescan_after_import": self.drive_selector.get_auto_rescan(),
                "rescan_full_drive": getattr(self, "_rescan_full_drive", False),
            }
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            logging.warning(f"Could not save config file: {e}")

    def start_backup(self):
        """Validates inputs and starts BackupWorker thread."""
        source_location = self.drive_selector.get_selected_drive_path()
        target_dir = self.drive_selector.get_target_directory()
        suffix = self.drive_selector.get_custom_suffix()
        folder_opts = self.drive_selector.get_selected_options()
        is_move = self.drive_selector.get_is_move_mode()

        if not source_location:
            self.alert_banner.show_alert("Please select a valid source drive, mobile phone, or folder.", level="ERROR")
            return

        if not is_mtp_path(source_location) and not os.path.exists(source_location):
            self.alert_banner.show_alert(f"Source location '{source_location}' does not exist.", level="ERROR")
            return

        if not target_dir:
            self.alert_banner.show_alert("Please select a target backup destination directory.", level="ERROR")
            return

        self.save_config()
        self.alert_banner.dismiss()
        self.progress_panel.reset_progress()
        self.log_console.clear()

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.worker = BackupWorker(
            source_card_path=source_location,
            target_dir=target_dir,
            fastcopy_path=self.fastcopy_path,
            custom_suffix=suffix,
            folder_opts=folder_opts,
            move_mode=is_move,
            auto_rescan=self.drive_selector.get_auto_rescan(),
            rescan_full_drive=getattr(self, "_rescan_full_drive", False),
        )

        # Wire worker signals to GUI
        self.worker.signals.scan_started.connect(self._on_scan_started)
        self.worker.signals.scan_progress.connect(self._on_scan_progress)
        self.worker.signals.duplicate_found.connect(self._on_duplicate_found)
        self.worker.signals.transfer_started.connect(self._on_transfer_started)
        self.worker.signals.transfer_progress.connect(self._on_transfer_progress)
        self.worker.signals.transfer_metrics.connect(self._on_transfer_metrics)
        self.worker.signals.transfer_line.connect(self._on_transfer_line)
        self.worker.signals.read_error.connect(self._on_read_error)
        self.worker.signals.finished.connect(self._on_backup_finished)
        self.worker.signals.error.connect(self._on_backup_error)

        self.worker.start()

    def cancel_backup(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_console.append_trace("⚠️ Backup cancellation requested by user...")
            self.cancel_btn.setEnabled(False)

    def _on_scan_started(self, scan_root: str):
        self.progress_panel.status_label.setText(f"Status: Scanning files in {scan_root}...")
        self.log_console.append_trace(f"🔍 Scan started: {scan_root}")

    def _on_scan_progress(self, current: int, total: int, filename: str):
        self.progress_panel.update_scan_progress(current, total, filename)

    def _on_duplicate_found(self, filename: str, hash_val: str, size: float):
        self.log_console.add_duplicate(filename, hash_val, int(size))

    def _on_transfer_started(self, total_files: int, total_bytes: float):
        self.progress_panel.reset_for_transfer(total_files, total_bytes)
        gb = total_bytes / (1024 ** 3)
        if self.worker and self.worker.is_mtp:
            mode_str = "MTP Phone Stream Transfer"
        elif self.worker and self.worker.move_mode:
            mode_str = "Same-Drive Instant Move"
        else:
            mode_str = "FastCopy Batch Transfer"
        self.log_console.append_trace(f"🚀 {mode_str} phase started ({total_files} files, {gb:.2f} GB)")

    def _on_transfer_progress(self, copied_count: int, total_files: int, current_filename: str, file_pct: int):
        self.progress_panel.update_transfer_progress(copied_count, total_files, current_filename, file_pct)

    def _on_transfer_metrics(self, metrics: dict):
        self.progress_panel.update_realtime_metrics(metrics)

    def _on_transfer_line(self, line: str):
        self.log_console.append_trace(line)

    def _on_read_error(self, file_path: str, err_msg: str):
        msg = f"Read Error on '{os.path.basename(file_path)}': {err_msg}"
        self.alert_banner.show_alert(msg, level="WARNING")

    def _on_backup_finished(self, summary: dict):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_panel.overall_bar.setValue(100)
        self.progress_panel.file_bar.setValue(100)
        
        mode_str = "Move" if (self.worker and self.worker.move_mode) else "Backup"
        self.progress_panel.status_label.setText(f"Status: {mode_str} Completed Successfully 🎉")

        scanned = summary.get("scanned", 0)
        copied = summary.get("copied", 0)
        dups = summary.get("duplicates", 0)
        gb = summary.get("bytes", 0) / (1024 ** 3)
        errs = summary.get("errors", 0)

        details = f"Scanned: {scanned} | Processed: {copied} | Skipped Duplicates: {dups} | {gb:.2f} GB"
        if errs > 0:
            details += f" | Errors: {errs}"
        self.progress_panel.update_details(f"{copied} processed", f"{gb:.2f} GB")

        self.log_console.append_trace(f"✅ OPERATION COMPLETE: {details}")
        
        # Auto-refresh database catalog tab
        target_dir = self.drive_selector.get_target_directory()
        self.db_catalog_widget.set_target_dir(target_dir)

    def _on_backup_error(self, fatal_err: str):
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.alert_banner.show_alert(f"Fatal Error: {fatal_err}", level="ERROR")
        self.log_console.append_trace(f"🛑 FATAL ERROR: {fatal_err}")

    def stop_threads(self):
        """Safely terminates all background child threads."""
        if hasattr(self, "drive_selector") and self.drive_selector:
            self.drive_selector.stop_threads()
        if hasattr(self, "db_catalog_widget") and self.db_catalog_widget:
            self.db_catalog_widget.stop_threads()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(1000)

    def closeEvent(self, event):
        """Save preferences and stop workers on window exit."""
        self.save_config()
        self.stop_threads()
        event.accept()

    def __del__(self):
        try:
            self.stop_threads()
        except Exception:
            pass
