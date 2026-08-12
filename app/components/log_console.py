"""
Dual Console Log Component for SD-FastBackup.
Tab 1: Duplicates Log (Table of skipped duplicates)
Tab 2: System Trace (Streaming FastCopy & metadata logs)
"""
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QPlainTextEdit, QHeaderView
)
from PySide6.QtCore import Qt


class LogConsoleWidget(QTabWidget):
    """Dual-Tab Output Console for Duplicates and System Trace Logging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        # Tab 1: Duplicates Log Table
        self.duplicate_widget = QWidget()
        dup_layout = QVBoxLayout(self.duplicate_widget)
        dup_layout.setContentsMargins(4, 4, 4, 4)

        self.duplicate_table = QTableWidget(0, 4)
        self.duplicate_table.setHorizontalHeaderLabels(["Filename", "Composite Hash", "Size (Bytes)", "Time Detected"])
        header = self.duplicate_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        dup_layout.addWidget(self.duplicate_table)
        self.addTab(self.duplicate_widget, "Duplicates Log (Skipped)")

        # Tab 2: System Trace Stream
        self.trace_widget = QWidget()
        trace_layout = QVBoxLayout(self.trace_widget)
        trace_layout.setContentsMargins(4, 4, 4, 4)

        self.trace_edit = QPlainTextEdit()
        self.trace_edit.setReadOnly(True)
        self.trace_edit.setMaximumBlockCount(5000)  # Limit line memory
        trace_layout.addWidget(self.trace_edit)

        self.addTab(self.trace_widget, "System Trace (FastCopy / Debug)")

    def add_duplicate(self, filename: str, hash_val: str, size: int):
        """Appends a skipped duplicate entry to Tab 1 table."""
        row = self.duplicate_table.rowCount()
        self.duplicate_table.insertRow(row)

        fn_item = QTableWidgetItem(filename)
        hash_item = QTableWidgetItem(hash_val[:16] + "...")
        hash_item.setToolTip(hash_val)
        size_item = QTableWidgetItem(f"{size:,}")
        time_item = QTableWidgetItem(datetime.now().strftime("%H:%M:%S"))

        for item in (fn_item, hash_item, size_item, time_item):
            item.setFlags(item.flags() ^ Qt.ItemIsEditable)

        self.duplicate_table.setItem(row, 0, fn_item)
        self.duplicate_table.setItem(row, 1, hash_item)
        self.duplicate_table.setItem(row, 2, size_item)
        self.duplicate_table.setItem(row, 3, time_item)

    def append_trace(self, text: str):
        """Appends a line or block of text to Tab 2 System Trace stream."""
        self.trace_edit.appendPlainText(text)
        # Auto scroll to bottom
        sb = self.trace_edit.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear(self):
        """Clears both log viewers."""
        self.duplicate_table.setRowCount(0)
        self.trace_edit.clear()
