"""
Media Extension Filter Configuration Dialog for SD-FastBackup.
Allows users to view, enable/disable, add custom extensions, and manage
whitelisted media formats (Photos/RAW, Videos, Audio, Camera Sidecars, Custom).
"""
import os
import json
from typing import Set, Dict, List, Optional
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QScrollArea, QTabWidget,
    QGridLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from utils.media_filter import (
    get_active_media_extensions, set_active_media_extensions,
    add_media_extension, remove_media_extension, reset_default_media_extensions,
    normalize_extension, DEFAULT_IMAGE_EXTENSIONS, DEFAULT_VIDEO_EXTENSIONS,
    DEFAULT_AUDIO_EXTENSIONS, DEFAULT_SIDECAR_EXTENSIONS, DEFAULT_MEDIA_EXTENSIONS
)
from utils.resource_path import get_config_path


class MediaExtensionFilterDialog(QDialog):
    """Configuration Dialog for viewing and toggling whitelisted media file extensions."""

    extensions_updated = Signal(set)
    extensions_changed = extensions_updated

    def __init__(self, config_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Media File Extension Filter")
        self.resize(680, 560)
        self.setMinimumSize(540, 440)
        self.config_path = config_path or get_config_path()
        
        # Local working set of enabled extensions
        self.working_extensions: Set[str] = get_active_media_extensions()
        self.checkbox_map: Dict[str, QCheckBox] = {}
        
        self._init_ui()
        self._sync_checkbox_states()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(14, 14, 14, 14)

        # Header Title & Description
        header_box = QVBoxLayout()
        title_label = QLabel("📁 Media File Formats & Extensions Whitelist")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #00ADB5;")
        desc_label = QLabel(
            "Only files matching checked extensions will be scanned, copied, and cataloged. "
            "All other files (e.g. Lightroom catalogs, system DBs, files with no extension) are strictly ignored."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #AAAAAA; font-size: 12px; margin-bottom: 4px;")
        header_box.addWidget(title_label)
        header_box.addWidget(desc_label)
        layout.addLayout(header_box)

        # Tabs by Category
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet("""
            QTabBar::tab {
                background-color: #2A2A2A;
                color: #BBBBBB;
                padding: 6px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background-color: #00ADB5;
                color: #FFFFFF;
            }
        """)

        # 1. Images & RAW Tab
        self.tab_widget.addTab(self._create_category_tab("Photos & RAW", DEFAULT_IMAGE_EXTENSIONS), "📷 Photos & RAW")

        # 2. Videos Tab
        self.tab_widget.addTab(self._create_category_tab("Videos", DEFAULT_VIDEO_EXTENSIONS), "🎥 Videos")

        # 3. Audio Tab
        self.tab_widget.addTab(self._create_category_tab("Audio", DEFAULT_AUDIO_EXTENSIONS), "🎵 Audio")

        # 4. Sidecars Tab
        self.tab_widget.addTab(self._create_category_tab("Camera Sidecars", DEFAULT_SIDECAR_EXTENSIONS), "📎 Camera Sidecars")

        # 5. Custom Extensions Tab
        self.custom_tab = self._create_custom_tab()
        self.tab_widget.addTab(self.custom_tab, "➕ Custom Extensions")

        layout.addWidget(self.tab_widget, 1)

        # Add Custom Extension Row
        add_box = QHBoxLayout()
        add_label = QLabel("Add New Extension:")
        add_label.setStyleSheet("font-weight: bold;")
        self.new_ext_input = QLineEdit()
        self.new_ext_input.setPlaceholderText("e.g. .braw, .insp, .dng")
        self.new_ext_input.returnPressed.connect(self._on_add_custom_extension)

        btn_add = QPushButton("➕ Add Format")
        btn_add.setStyleSheet("background-color: #00ADB5; color: white; font-weight: bold; padding: 5px 14px;")
        btn_add.clicked.connect(self._on_add_custom_extension)

        add_box.addWidget(add_label)
        add_box.addWidget(self.new_ext_input, 1)
        add_box.addWidget(btn_add)
        layout.addLayout(add_box)

        # Active Count & Action Buttons
        bottom_box = QHBoxLayout()
        self.count_label = QLabel(f"Active Formats: {len(self.working_extensions)} enabled")
        self.count_label.setStyleSheet("color: #00FFF5; font-weight: bold; font-size: 12px;")

        btn_reset = QPushButton("🔄 Reset Defaults")
        btn_reset.setToolTip("Restore standard built-in photo/video/audio extensions")
        btn_reset.clicked.connect(self._on_reset_defaults)

        btn_save = QPushButton("💾 Save & Apply")
        btn_save.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 7px 20px;")
        btn_save.clicked.connect(self._on_save_and_apply)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        bottom_box.addWidget(self.count_label)
        bottom_box.addStretch()
        bottom_box.addWidget(btn_reset)
        bottom_box.addWidget(btn_save)
        bottom_box.addWidget(btn_cancel)
        layout.addLayout(bottom_box)

    def _create_category_tab(self, category_name: str, extensions: Set[str]) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(8, 8, 8, 8)

        # Quick toggles row
        toggle_box = QHBoxLayout()
        lbl = QLabel(f"<b>{category_name} Formats:</b>")
        btn_all = QPushButton("Select All")
        btn_all.setFixedWidth(85)
        btn_none = QPushButton("Deselect All")
        btn_none.setFixedWidth(95)

        sorted_exts = sorted(list(extensions))
        btn_all.clicked.connect(lambda: self._set_category_state(sorted_exts, True))
        btn_none.clicked.connect(lambda: self._set_category_state(sorted_exts, False))

        toggle_box.addWidget(lbl)
        toggle_box.addStretch()
        toggle_box.addWidget(btn_all)
        toggle_box.addWidget(btn_none)
        vbox.addLayout(toggle_box)

        # Scrollable Grid of Checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)

        cols = 4
        for idx, ext in enumerate(sorted_exts):
            cb = QCheckBox(ext.upper())
            cb.setProperty("ext", ext)
            cb.stateChanged.connect(self._on_checkbox_toggled)
            self.checkbox_map[ext] = cb
            grid.addWidget(cb, idx // cols, idx % cols)

        scroll.setWidget(container)
        vbox.addWidget(scroll, 1)
        return widget

    def _create_custom_tab(self) -> QWidget:
        widget = QWidget()
        self.custom_vbox = QVBoxLayout(widget)
        self.custom_vbox.setContentsMargins(8, 8, 8, 8)

        lbl = QLabel("<b>Custom User-Added Formats:</b>")
        self.custom_vbox.addWidget(lbl)

        self.custom_scroll = QScrollArea()
        self.custom_scroll.setWidgetResizable(True)
        self.custom_scroll.setFrameShape(QFrame.NoFrame)

        self.custom_container = QWidget()
        self.custom_grid = QGridLayout(self.custom_container)
        self.custom_grid.setSpacing(8)
        self.custom_scroll.setWidget(self.custom_container)

        self.custom_vbox.addWidget(self.custom_scroll, 1)
        self._refresh_custom_tab()
        return widget

    def _refresh_custom_tab(self):
        # Clear existing custom grid items
        while self.custom_grid.count():
            item = self.custom_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Find custom extensions not in default sets
        custom_exts = sorted([e for e in self.working_extensions if e not in DEFAULT_MEDIA_EXTENSIONS])
        
        if not custom_exts:
            empty_lbl = QLabel("<i>No custom extensions added yet. Use the field below to add formats.</i>")
            empty_lbl.setStyleSheet("color: #777777;")
            self.custom_grid.addWidget(empty_lbl, 0, 0)
            return

        cols = 3
        for idx, ext in enumerate(custom_exts):
            item_box = QHBoxLayout()
            cb = QCheckBox(ext.upper())
            cb.setProperty("ext", ext)
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_checkbox_toggled)
            self.checkbox_map[ext] = cb

            btn_del = QPushButton("🗑️")
            btn_del.setFixedSize(24, 24)
            btn_del.setToolTip(f"Delete {ext} format")
            btn_del.clicked.connect(lambda _, e=ext: self._on_delete_custom_extension(e))

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(cb, 1)
            row_layout.addWidget(btn_del)

            self.custom_grid.addWidget(row_widget, idx // cols, idx % cols)

    def _sync_checkbox_states(self):
        for ext, cb in self.checkbox_map.items():
            cb.blockSignals(True)
            cb.setChecked(ext in self.working_extensions)
            cb.blockSignals(False)
        self._update_count_label()

    def _update_count_label(self):
        self.count_label.setText(f"Active Formats: {len(self.working_extensions)} enabled")

    def _on_checkbox_toggled(self, state):
        cb = self.sender()
        if not cb:
            return
        ext = cb.property("ext")
        if not ext:
            return

        if cb.isChecked():
            self.working_extensions.add(ext)
        else:
            self.working_extensions.discard(ext)

        self._update_count_label()

    def _set_category_state(self, exts: List[str], checked: bool):
        for ext in exts:
            if checked:
                self.working_extensions.add(ext)
            else:
                self.working_extensions.discard(ext)
            if ext in self.checkbox_map:
                self.checkbox_map[ext].blockSignals(True)
                self.checkbox_map[ext].setChecked(checked)
                self.checkbox_map[ext].blockSignals(False)
        self._update_count_label()

    def _on_add_custom_extension(self):
        raw = self.new_ext_input.text().strip()
        if not raw:
            return

        # Split multiple comma or space separated extensions
        tokens = [t.strip() for t in raw.replace(',', ' ').split() if t.strip()]
        added = []
        for t in tokens:
            norm = normalize_extension(t)
            if norm and norm != '.':
                self.working_extensions.add(norm)
                added.append(norm)

        self.new_ext_input.clear()
        self._refresh_custom_tab()
        self._sync_checkbox_states()

    def _on_delete_custom_extension(self, ext: str):
        self.working_extensions.discard(ext)
        if ext in self.checkbox_map:
            del self.checkbox_map[ext]
        self._refresh_custom_tab()
        self._update_count_label()

    def _on_reset_defaults(self):
        reply = QMessageBox.question(
            self,
            "Reset Defaults",
            "Are you sure you want to reset media extension filters to factory defaults?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.working_extensions = set(DEFAULT_MEDIA_EXTENSIONS)
            self._refresh_custom_tab()
            self._sync_checkbox_states()

    def _on_save_and_apply(self):
        if not self.working_extensions:
            QMessageBox.warning(self, "Selection Required", "Please select at least one media extension to allow.")
            return

        # 1. Update runtime active extensions set
        set_active_media_extensions(self.working_extensions)

        # 2. Persist in config.json
        try:
            cfg = {}
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

            cfg["media_extensions"] = sorted(list(self.working_extensions))

            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)

        except Exception as e:
            QMessageBox.warning(self, "Save Notice", f"Could not save extensions to config.json: {e}")

        self.extensions_updated.emit(set(self.working_extensions))
        self.accept()
