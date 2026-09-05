"""
PySide6 Index Media Folder Dialog & Background Worker for SD-FastBackup.
Allows users to select an arbitrary media folder and index all images/videos
in-place into a compliant .sd_backup_catalog.db for QuickImageCullLAN.
"""
import os
import logging
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QCheckBox, QGroupBox, QFileDialog,
    QMessageBox, QFormLayout
)
from PySide6.QtCore import Qt, QThread, Signal

from core.indexer import FolderIndexer
from utils.path_formatter import normalize_win_path


class IndexFolderWorker(QThread):
    """Background worker for executing in-place folder indexing."""
    progress_updated = Signal(dict)
    completed = Signal(dict)
    error_occurred = Signal(str)

    def __init__(
        self,
        folder_path: str,
        force_reextract: bool = False,
        include_subdirs: bool = True,
        parent=None
    ):
        super().__init__(parent)
        self.folder_path = folder_path
        self.force_reextract = force_reextract
        self.include_subdirs = include_subdirs
        self._is_cancelled = False

    def cancel(self):
        """Requests graceful cancellation of the indexing operation."""
        self._is_cancelled = True

    def run(self):
        try:
            stats = FolderIndexer.index_folder(
                root_dir=self.folder_path,
                progress_callback=self._on_progress,
                is_cancelled=lambda: self._is_cancelled,
                force_reextract=self.force_reextract,
                include_subdirs=self.include_subdirs
            )
            self.completed.emit(stats)
        except Exception as e:
            logging.exception("Error during folder indexing")
            self.error_occurred.emit(str(e))

    def _on_progress(self, data: dict):
        self.progress_updated.emit(data)


class IndexFolderDialog(QDialog):
    """Modal dialog to index an existing media folder in-place into .sd_backup_catalog.db."""

    folder_indexed = Signal(str)

    def __init__(self, initial_folder: str = "", parent=None):
        super().__init__(parent)
        self.initial_folder = initial_folder
        self.indexed_folder_path = ""
        self._worker: Optional[IndexFolderWorker] = None

        self.setWindowTitle("Index Media Folder (Create Database)")
        self.resize(600, 360)
        self.setMinimumSize(540, 320)

        self._init_ui()

    def stop_threads(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.quit()
            self._worker.wait(1500)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Indexing?",
                "Indexing is currently in progress. Do you want to cancel?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.stop_threads()
                super().closeEvent(event)
            else:
                event.ignore()
                return
        else:
            self.stop_threads()
            super().closeEvent(event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Header Description
        header_label = QLabel(
            "<b>Index Any Media Folder In-Place</b><br>"
            "<span style='color: #888888; font-size: 11px;'>"
            "Generates or updates <code>.sd_backup_catalog.db</code> with composite hashes, EXIF/MediaInfo, "
            "and QuickImageCullLAN compatibility without copying or moving files."
            "</span>"
        )
        header_label.setTextFormat(Qt.RichText)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Folder Selection Group
        folder_group = QGroupBox("Target Media Folder")
        folder_layout = QHBoxLayout(folder_group)

        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Select or enter path to media folder (e.g. D:\\Photos\\2026_Shoot)...")
        if self.initial_folder and os.path.exists(self.initial_folder):
            self.folder_input.setText(normalize_win_path(self.initial_folder))

        btn_browse = QPushButton("📁 Browse...")
        btn_browse.clicked.connect(self._browse_folder)

        folder_layout.addWidget(self.folder_input, 1)
        folder_layout.addWidget(btn_browse)
        layout.addWidget(folder_group)

        # Options Group
        opts_group = QGroupBox("Indexing Options")
        opts_layout = QVBoxLayout(opts_group)

        self.chk_subdirs = QCheckBox("Recursively index nested subdirectories")
        self.chk_subdirs.setChecked(True)
        opts_layout.addWidget(self.chk_subdirs)

        self.chk_force_reextract = QCheckBox("Force re-extract all EXIF / MediaInfo (slower, updates existing records)")
        self.chk_force_reextract.setChecked(False)
        opts_layout.addWidget(self.chk_force_reextract)

        layout.addWidget(opts_group)

        # Progress / Status Section
        progress_group = QGroupBox("Indexing Progress")
        progress_layout = QVBoxLayout(progress_group)

        self.status_label = QLabel("Ready to index.")
        self.status_label.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        progress_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #333333;
                border-radius: 4px;
                text-align: center;
                background-color: #1E1E1E;
                color: #FFFFFF;
                font-weight: bold;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #00ADB5;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        self.stats_label = QLabel("Discovered: 0 | Added: 0 | Skipped: 0 | Metadata: 0")
        self.stats_label.setStyleSheet("color: #00ADB5; font-size: 11px; font-weight: bold;")
        progress_layout.addWidget(self.stats_label)

        layout.addWidget(progress_group)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_start = QPushButton("🚀 START INDEXING")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #00ADB5;
                color: #FFFFFF;
                font-weight: bold;
                padding: 8px 18px;
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
        self.btn_start.clicked.connect(self._on_start_clicked)

        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def _browse_folder(self):
        initial = self.folder_input.text().strip() or self.initial_folder or os.getcwd()
        selected = QFileDialog.getExistingDirectory(self, "Select Media Folder to Index", initial)
        if selected:
            self.folder_input.setText(normalize_win_path(selected))

    def _on_start_clicked(self):
        folder_p = self.folder_input.text().strip()
        if not folder_p:
            QMessageBox.warning(self, "Folder Required", "Please select a valid media folder to index.")
            return

        norm_folder = normalize_win_path(os.path.abspath(folder_p))
        if not os.path.exists(norm_folder) or not os.path.isdir(norm_folder):
            QMessageBox.warning(self, "Invalid Folder", f"Folder path '{norm_folder}' does not exist or is not a directory.")
            return

        self.indexed_folder_path = norm_folder
        self.btn_start.setEnabled(False)
        self.folder_input.setEnabled(False)
        self.chk_subdirs.setEnabled(False)
        self.chk_force_reextract.setEnabled(False)
        self.btn_cancel.setText("⛔ Cancel")

        self.progress_bar.setRange(0, 0) # Indeterminate while discovering
        self.status_label.setText("⏳ Discovering media files in folder...")
        self.stats_label.setText("Discovered: 0 | Added: 0 | Skipped: 0 | Metadata: 0")

        self._worker = IndexFolderWorker(
            folder_path=norm_folder,
            force_reextract=self.chk_force_reextract.isChecked(),
            include_subdirs=self.chk_subdirs.isChecked(),
            parent=self
        )
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.completed.connect(self._on_indexing_completed)
        self._worker.error_occurred.connect(self._on_indexing_error)
        self._worker.start()

    def _on_cancel_clicked(self):
        if self._worker and self._worker.isRunning():
            self.status_label.setText("Stopping indexing...")
            self.btn_cancel.setEnabled(False)
            self._worker.cancel()
        else:
            self.reject()

    def _on_progress_updated(self, data: dict):
        status = data.get("status", "")
        if status == "DISCOVERING":
            self.progress_bar.setRange(0, 0)
            self.status_label.setText("Discovering media files...")
        elif status == "INDEXING":
            current = data.get("current", 0)
            total = data.get("total", 0)
            if total > 0:
                self.progress_bar.setRange(0, total)
                self.progress_bar.setValue(current)
            
            cur_file = data.get("current_file", "")
            self.status_label.setText(f"Indexing ({current}/{total}): {cur_file}")
            
            added = data.get("added", 0)
            skipped = data.get("skipped", 0)
            meta = data.get("metadata_extracted", 0)
            errors = data.get("errors", 0)
            self.stats_label.setText(
                f"Discovered: {total} | Added: {added} | Skipped: {skipped} | Metadata: {meta}" +
                (f" | Errors: {errors}" if errors > 0 else "")
            )

    def _on_indexing_completed(self, stats: dict):
        self.btn_start.setEnabled(True)
        self.folder_input.setEnabled(True)
        self.chk_subdirs.setEnabled(True)
        self.chk_force_reextract.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("Close")

        total = stats.get("total_discovered", 0)
        self.progress_bar.setRange(0, total if total > 0 else 1)
        self.progress_bar.setValue(total if total > 0 else 1)

        if stats.get("cancelled", False):
            self.status_label.setText("⚠️ Indexing cancelled by user.")
            QMessageBox.warning(self, "Indexing Cancelled", "Folder indexing was stopped before completion.")
            return

        self.status_label.setText("✅ Indexing completed successfully!")
        msg = (
            f"Folder Indexing Complete! 🎉\n\n"
            f"• Target Folder: {self.indexed_folder_path}\n"
            f"• Total Discovered Media: {stats['total_discovered']}\n"
            f"• New Records Cataloged: {stats['added_records']}\n"
            f"• Existing Records Skipped: {stats['skipped_records']}\n"
            f"• Metadata Extracted: {stats['metadata_extracted']}"
        )
        if stats.get("errors", 0) > 0:
            msg += f"\n• Errors: {stats['errors']}"

        msg += "\n\nThe folder catalog (.sd_backup_catalog.db) is ready for QuickImageCullLAN."

        QMessageBox.information(self, "Indexing Successful", msg)
        self.folder_indexed.emit(self.indexed_folder_path)
        self.accept()

    def _on_indexing_error(self, err_msg: str):
        self.btn_start.setEnabled(True)
        self.folder_input.setEnabled(True)
        self.chk_subdirs.setEnabled(True)
        self.chk_force_reextract.setEnabled(True)
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("Close")
        self.progress_bar.setRange(0, 100)
        self.status_label.setText(f"❌ Error: {err_msg}")
        QMessageBox.critical(self, "Indexing Error", f"Failed to index folder: {err_msg}")
