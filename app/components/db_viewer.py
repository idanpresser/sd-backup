"""
PySide6 Database Catalog Manager GUI, Suffix Renamer Dialog & Sync Dialog for SD-FastBackup.
Provides catalog table browsing, debounced search filtering, metadata inspection,
batch suffix renaming, single/batch row purging, and disk-catalog synchronization.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QTextEdit, QMessageBox, QCheckBox, QGroupBox, QListWidget, QListWidgetItem,
    QFileDialog, QFormLayout
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from core.db import DatabaseManager
from core.sync_engine import calculate_sync_diff, execute_sync
from utils.maintenance import rename_suffix_in_backup


class SuffixRenamerDialog(QDialog):
    """Modal dialog for batch renaming file suffixes on disk and updating SQLite database catalog."""

    def __init__(self, target_dir: str, parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self.setWindowTitle("Batch Suffix Renamer")
        self.resize(520, 260)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel(f"<b>Target Backup Directory:</b> {self.target_dir}")
        info_label.setStyleSheet("font-size: 13px; margin-bottom: 5px;")
        layout.addWidget(info_label)

        form_layout = QFormLayout()

        self.old_suffix_input = QLineEdit()
        self.old_suffix_input.setPlaceholderText("e.g. AnatKP(C)")
        form_layout.addRow("Old Suffix to Replace:", self.old_suffix_input)

        self.new_suffix_input = QLineEdit()
        self.new_suffix_input.setPlaceholderText("e.g. IdanPresser(C)")
        form_layout.addRow("New Replacement Suffix:", self.new_suffix_input)

        file_list_layout = QHBoxLayout()
        self.file_list_input = QLineEdit()
        self.file_list_input.setPlaceholderText("Optional text file listing specific files...")
        btn_browse_list = QPushButton("Browse...")
        btn_browse_list.clicked.connect(self._browse_file_list)
        file_list_layout.addWidget(self.file_list_input, 1)
        file_list_layout.addWidget(btn_browse_list)

        form_layout.addRow("File List (Optional):", file_list_layout)
        layout.addLayout(form_layout)

        layout.addSpacing(10)

        btn_box = QHBoxLayout()
        self.btn_run = QPushButton("⚡ Execute Rename")
        self.btn_run.setStyleSheet("background-color: #00ADB5; color: white; font-weight: bold; padding: 7px 16px;")
        self.btn_run.clicked.connect(self._on_execute_rename)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_run)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _browse_file_list(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select File List", self.target_dir, "Text Files (*.txt);;All Files (*.*)"
        )
        if path:
            self.file_list_input.setText(path)

    def _on_execute_rename(self):
        old_suf = self.old_suffix_input.text().strip()
        new_suf = self.new_suffix_input.text().strip()
        file_list = self.file_list_input.text().strip() or None

        if not old_suf:
            QMessageBox.warning(self, "Input Required", "Please enter the old suffix to replace.")
            return

        try:
            stats = rename_suffix_in_backup(
                root_dir=self.target_dir,
                old_suffix=old_suf,
                new_suffix=new_suf,
                file_list_path=file_list
            )

            msg = (
                f"Suffix Rename Operation Complete! 🎉\n\n"
                f"• Scanned Files: {stats['scanned_count']}\n"
                f"• Files Renamed: {stats['renamed_count']}\n"
                f"• DB Catalog Records Updated: {stats['db_updated_count']}"
            )
            if stats['errors'] > 0:
                msg += f"\n• Errors: {stats['errors']}"

            QMessageBox.information(self, "Rename Success", msg)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Rename Error", f"Failed to execute suffix rename: {e}")


class DBSyncDialog(QDialog):
    """Modal dialog presenting DB-Disk Synchronization preview diff and options."""

    def __init__(self, target_dir: str, parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self.setWindowTitle("Database & Disk Synchronization")
        self.resize(750, 500)
        self._init_ui()
        self._load_preview()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        header_label = QLabel(f"<b>Sync Target Directory:</b> {self.target_dir}")
        header_label.setStyleSheet("font-size: 13px; margin-bottom: 5px;")
        layout.addWidget(header_label)

        # Lists preview
        splitter = QSplitter(Qt.Horizontal)

        # Left: Missing files
        left_group = QGroupBox("Missing Files (In DB catalog, absent on disk)")
        left_box = QVBoxLayout(left_group)
        self.missing_list = QListWidget()
        left_box.addWidget(self.missing_list)
        splitter.addWidget(left_group)

        # Right: Uncataloged files
        right_group = QGroupBox("Uncataloged Files (On disk, missing from DB catalog)")
        right_box = QVBoxLayout(right_group)
        self.uncataloged_list = QListWidget()
        right_box.addWidget(self.uncataloged_list)
        splitter.addWidget(right_group)

        layout.addWidget(splitter, 1)

        # Options
        options_layout = QHBoxLayout()
        self.chk_remove_missing = QCheckBox("Purge missing file records from DB catalog")
        self.chk_remove_missing.setChecked(True)
        self.chk_add_uncataloged = QCheckBox("Index uncataloged disk files into DB catalog")
        self.chk_add_uncataloged.setChecked(True)

        options_layout.addWidget(self.chk_remove_missing)
        options_layout.addWidget(self.chk_add_uncataloged)
        layout.addLayout(options_layout)

        # Buttons
        btn_box = QHBoxLayout()
        self.btn_apply = QPushButton("⚡ Apply Synchronization")
        self.btn_apply.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_apply.clicked.connect(self._on_apply_sync)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_apply)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)

    def _load_preview(self):
        try:
            diff = calculate_sync_diff(self.target_dir)
            self.missing_list.clear()
            self.uncataloged_list.clear()

            for item in diff["missing_records"]:
                text = f"❌ {item['original_filename']} ({item['destination_path']})"
                self.missing_list.addItem(QListWidgetItem(text))

            for item in diff["uncataloged_files"]:
                text = f"➕ {os.path.basename(item['file_path'])} ({item['relative_path']})"
                self.uncataloged_list.addItem(QListWidgetItem(text))

            missing_cnt = len(diff["missing_records"])
            uncat_cnt = len(diff["uncataloged_files"])
            if missing_cnt == 0 and uncat_cnt == 0:
                self.missing_list.addItem("✅ Catalog is fully synchronized with disk!")
                self.btn_apply.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Sync Preview Error", f"Failed to compute sync diff: {e}")

    def _on_apply_sync(self):
        remove_missing = self.chk_remove_missing.isChecked()
        add_uncataloged = self.chk_add_uncataloged.isChecked()

        if not remove_missing and not add_uncataloged:
            QMessageBox.information(self, "No Options Selected", "Please check at least one sync action.")
            return

        try:
            stats = execute_sync(
                self.target_dir,
                remove_missing=remove_missing,
                add_uncataloged=add_uncataloged
            )
            msg = f"Synchronization Complete!\n\n• Removed Records: {stats['removed_records']}\n• Added Records: {stats['added_records']}"
            if stats['errors'] > 0:
                msg += f"\n• Errors: {stats['errors']}"
            QMessageBox.information(self, "Sync Success", msg)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Sync Failed", f"Failed to execute synchronization: {e}")


class DBCatalogWidget(QWidget):
    """Main Database Catalog Manager Widget designed for embedding inside QTabWidget."""

    def __init__(self, target_dir: str = "", parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        self.db: Optional[DatabaseManager] = DatabaseManager(self.target_dir) if (self.target_dir and os.path.exists(self.target_dir)) else None
        self.rows_data: List[Dict[str, Any]] = []

        # Debounced search timer (400ms delay to avoid stutter while typing/backspacing)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(400)
        self.search_timer.timeout.connect(self._apply_filter)

        self._init_ui()
        if self.target_dir:
            self.reload_catalog()

    def set_target_dir(self, target_dir: str):
        """Updates target directory and reloads catalog database."""
        if self.target_dir != target_dir:
            self.target_dir = target_dir
            if self.target_dir and os.path.exists(self.target_dir):
                self.db = DatabaseManager(self.target_dir)
            else:
                self.db = None
            self.reload_catalog()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Top Control Bar: Directory label + Search input + Buttons
        top_bar = QHBoxLayout()
        self.dir_label = QLabel(f"<b>Catalog:</b> {os.path.basename(self.target_dir) or 'No target selected'}/")
        self.dir_label.setStyleSheet("font-size: 13px;")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search by filename, date taken, camera model, or copy status...")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._apply_filter)

        btn_renamer = QPushButton("✏️ Batch Rename Suffixes...")
        btn_renamer.setToolTip("Rename file suffixes on disk and update SQLite database catalog")
        btn_renamer.clicked.connect(self._open_renamer_dialog)

        btn_sync = QPushButton("🔄 Sync with Disk...")
        btn_sync.setToolTip("Compare database catalog against target files on disk")
        btn_sync.clicked.connect(self._open_sync_dialog)

        btn_refresh = QPushButton("⚡ Refresh")
        btn_refresh.clicked.connect(self.reload_catalog)

        top_bar.addWidget(self.dir_label)
        top_bar.addWidget(self.search_input, 1)
        top_bar.addWidget(btn_renamer)
        top_bar.addWidget(btn_sync)
        top_bar.addWidget(btn_refresh)
        main_layout.addLayout(top_bar)

        # Center Splitter: Table (Left) + Inspector Panel (Right)
        splitter = QSplitter(Qt.Horizontal)

        # Table Widget
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Original Filename", "Relative Path", "Size (MB)", "Date Taken", "Camera Model", "Copy Status"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        # Inspector Panel
        inspector_group = QGroupBox("Metadata Inspector")
        inspector_layout = QVBoxLayout(inspector_group)

        self.inspector_text = QTextEdit()
        self.inspector_text.setReadOnly(True)
        self.inspector_text.setPlaceholderText("Select a row in the table to inspect detailed EXIF/MediaInfo metadata...")
        inspector_layout.addWidget(self.inspector_text)

        splitter.addWidget(inspector_group)
        splitter.setSizes([750, 350])
        main_layout.addWidget(splitter, 1)

        # Bottom Bar: Row count + Delete Button
        bottom_bar = QHBoxLayout()
        self.status_label = QLabel("0 records")
        self.status_label.setStyleSheet("color: #7f8c8d;")

        btn_delete = QPushButton("🗑️ Purge Selected Record")
        btn_delete.setStyleSheet("background-color: #c0392b; color: white; padding: 5px 12px;")
        btn_delete.clicked.connect(self._on_delete_selected)

        bottom_bar.addWidget(self.status_label)
        bottom_bar.addStretch()
        bottom_bar.addWidget(btn_delete)
        main_layout.addLayout(bottom_bar)

    def _on_search_text_changed(self):
        """Restarts the 400ms single-shot timer to debounce typing/backspacing."""
        self.search_timer.start()

    def reload_catalog(self):
        self.table.setRowCount(0)
        self.rows_data.clear()

        dir_name = os.path.basename(self.target_dir) if self.target_dir else "No target selected"
        self.dir_label.setText(f"<b>Catalog:</b> {dir_name}/")

        if not self.target_dir or not os.path.exists(self.target_dir):
            self.status_label.setText("Select a valid target backup directory to view catalog.")
            return

        if not self.db:
            self.db = DatabaseManager(self.target_dir)

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        fc.file_id, fc.composite_hash, fc.original_filename, fc.relative_path,
                        fc.file_size_bytes, fc.date_taken, fc.date_taken_source,
                        tm.copy_status, tm.destination_path,
                        fm.camera_make, fm.camera_model, fm.lens_model, fm.serial_number,
                        fm.iso, fm.aperture, fm.shutter_speed, fm.focal_length, fm.white_balance,
                        fm.width, fm.height, fm.aspect_ratio, fm.color_space,
                        fm.video_codec, fm.container_format, fm.frame_rate, fm.duration_seconds,
                        fm.bitrate, fm.audio_codec, fm.audio_channels, fm.audio_sample_rate,
                        fm.latitude, fm.longitude, fm.altitude, fm.raw_json
                    FROM file_catalog fc
                    LEFT JOIN transfer_manifest tm ON fc.composite_hash = tm.composite_hash
                    LEFT JOIN file_metadata fm ON fc.composite_hash = fm.composite_hash
                    ORDER BY fc.file_id DESC
                """)
                rows = cursor.fetchall()
                for row in rows:
                    self.rows_data.append(dict(row))

            self.table.setRowCount(len(self.rows_data))
            for i, row in enumerate(self.rows_data):
                file_id = str(row["file_id"])
                fname = row["original_filename"] or ""
                rel_p = row["relative_path"] or ""
                size_mb = f"{(row['file_size_bytes'] or 0) / (1024*1024):.2f}"
                dt_taken = str(row["date_taken"] or "")
                camera = f"{row['camera_make'] or ''} {row['camera_model'] or ''}".strip() or "-"
                status = row["copy_status"] or "UNKNOWN"

                self.table.setItem(i, 0, QTableWidgetItem(file_id))
                self.table.setItem(i, 1, QTableWidgetItem(fname))
                self.table.setItem(i, 2, QTableWidgetItem(rel_p))
                self.table.setItem(i, 3, QTableWidgetItem(size_mb))
                self.table.setItem(i, 4, QTableWidgetItem(dt_taken))
                self.table.setItem(i, 5, QTableWidgetItem(camera))
                self.table.setItem(i, 6, QTableWidgetItem(status))

            self._apply_filter()

        except Exception as e:
            QMessageBox.critical(self, "Catalog Error", f"Failed to query database catalog: {e}")

    def _apply_filter(self):
        query = self.search_input.text().strip().lower()
        visible_cnt = 0

        for i in range(self.table.rowCount()):
            row_data = self.rows_data[i]
            search_blob = f"{row_data['original_filename']} {row_data['relative_path']} {row_data['date_taken']} {row_data['camera_make']} {row_data['camera_model']} {row_data['copy_status']}".lower()

            if not query or query in search_blob:
                self.table.setRowHidden(i, False)
                visible_cnt += 1
            else:
                self.table.setRowHidden(i, True)

        self.status_label.setText(f"Showing {visible_cnt} of {len(self.rows_data)} records")

    def _on_row_selected(self):
        selected = self.table.selectedIndexes()
        if not selected:
            self.inspector_text.setPlainText("Select a row in the table to inspect detailed metadata...")
            return

        row_idx = selected[0].row()
        if row_idx >= len(self.rows_data):
            return

        data = self.rows_data[row_idx]
        lines = [
            f"<b>File Name:</b> {data['original_filename']}",
            f"<b>Composite Hash:</b> {data['composite_hash']}",
            f"<b>Relative Path:</b> {data['relative_path']}",
            f"<b>Size:</b> {data['file_size_bytes']} bytes ({(data['file_size_bytes'] or 0)/(1024*1024):.2f} MB)",
            f"<b>Date Taken:</b> {data['date_taken']} (Source: {data['date_taken_source']})",
            f"<b>Transfer Status:</b> {data['copy_status']}",
            f"<b>Destination Path:</b> {data['destination_path'] or 'N/A'}",
            "<hr>",
            "<b>📷 Camera & Lens Metadata:</b>",
            f"  • Make / Model: {data['camera_make'] or '-'} / {data['camera_model'] or '-'}",
            f"  • Lens: {data['lens_model'] or '-'}",
            f"  • Body Serial: {data['serial_number'] or '-'}",
            f"  • Exposure: ISO {data['iso'] or '-'}, {data['aperture'] or '-'}, {data['shutter_speed'] or '-'}, {data['focal_length'] or '-'}",
            f"  • White Balance: {data['white_balance'] or '-'}",
            f"  • Image Size: {data['width'] or '-'} x {data['height'] or '-'} ({data['aspect_ratio'] or '-'})",
            f"  • Color Space: {data['color_space'] or '-'}",
            "<hr>",
            "<b>🎥 Video Metadata:</b>",
            f"  • Codec / Format: {data['video_codec'] or '-'} / {data['container_format'] or '-'}",
            f"  • FPS / Bitrate: {data['frame_rate'] or '-'} FPS / {data['bitrate'] or '-'} bps",
            f"  • Duration: {data['duration_seconds'] or '-'} sec",
            f"  • Audio: {data['audio_codec'] or '-'}, {data['audio_channels'] or '-'} ch @ {data['audio_sample_rate'] or '-'} Hz",
            "<hr>",
            "<b>📍 Location:</b>",
            f"  • Lat / Lon / Alt: {data['latitude'] or '-'}, {data['longitude'] or '-'}, {data['altitude'] or '-'}",
            "<hr>",
            "<b>📦 Raw JSON Tags Dump:</b>"
        ]

        raw_json_str = data.get("raw_json") or "{}"
        try:
            pretty_json = json.dumps(json.loads(raw_json_str), indent=2)
            lines.append(f"<pre>{pretty_json}</pre>")
        except Exception:
            lines.append(f"<pre>{raw_json_str}</pre>")

        self.inspector_text.setHtml("<br>".join(lines))

    def _on_delete_selected(self):
        selected = self.table.selectedIndexes()
        if not selected:
            QMessageBox.information(self, "Select Record", "Please select a record row to delete.")
            return

        row_idx = selected[0].row()
        data = self.rows_data[row_idx]
        h_val = data["composite_hash"]
        fname = data["original_filename"]

        reply = QMessageBox.question(
            self,
            "Confirm Purge",
            f"Are you sure you want to purge catalog record '{fname}' (ID: {data['file_id']})?\n\nThis removes SQLite metadata records only.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes and self.db:
            try:
                self.db.delete_file_record(h_val)
                self.db.checkpoint()
                self.reload_catalog()
            except Exception as e:
                QMessageBox.critical(self, "Purge Error", f"Failed to delete record: {e}")

    def _open_renamer_dialog(self):
        if not self.target_dir or not os.path.exists(self.target_dir):
            QMessageBox.warning(self, "Target Required", "Please select a valid target backup directory first.")
            return
        dialog = SuffixRenamerDialog(self.target_dir, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.reload_catalog()

    def _open_sync_dialog(self):
        if not self.target_dir or not os.path.exists(self.target_dir):
            QMessageBox.warning(self, "Target Required", "Please select a valid target backup directory first.")
            return
        dialog = DBSyncDialog(self.target_dir, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.reload_catalog()


class DBCatalogDialog(QDialog):
    """Dialog wrapper around DBCatalogWidget for popup usage."""

    def __init__(self, target_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Database Catalog Manager")
        self.resize(1100, 650)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.catalog_widget = DBCatalogWidget(target_dir=target_dir, parent=self)
        layout.addWidget(self.catalog_widget)

        # Expose attributes for backward compatibility
        self.table = self.catalog_widget.table
        self.search_input = self.catalog_widget.search_input
        self._apply_filter = self.catalog_widget._apply_filter
