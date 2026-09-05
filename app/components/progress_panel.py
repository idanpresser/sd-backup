"""
Progress Panel Component for SD-FastBackup.
Displays Overall Progress %, Transfer Speed (MB/s), and Bytes Written / Total Bytes.

There is deliberately no per-file progress bar: no ingest engine exposes per-file byte
progress (FastCopy reports aggregate batch bytes, a same-volume move is a rename, and an
MTP copy is a single blocking COM call), so such a bar could only mirror overall progress
or sit pinned at 100%.
"""
from PySide6.QtWidgets import QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar


class ProgressPanelWidget(QGroupBox):
    """Overall Progress Meter & Transfer Speed Tracker Widget."""

    def __init__(self, parent=None):
        super().__init__("BACKUP PIPELINE PROGRESS", parent)
        self.total_bytes = 0
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 1. Status Label Row
        self.status_label = QLabel("Status: Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-weight: bold; color: #E0E0E0;")
        layout.addWidget(self.status_label)

        # 2. Overall Progress Meter
        overall_layout = QHBoxLayout()
        overall_title = QLabel("Overall Progress:")
        overall_title.setMinimumWidth(120)
        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, 100)
        self.overall_bar.setValue(0)
        overall_layout.addWidget(overall_title)
        overall_layout.addWidget(self.overall_bar, 1)
        layout.addLayout(overall_layout)

        # 3. Details / Speed Indicator
        self.details_label = QLabel("Files: 0 / 0 | Bytes: 0 B | Speed: --")
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("color: #00ADB5; font-size: 12px;")
        layout.addWidget(self.details_label)

    def reset_progress(self):
        self.total_bytes = 0
        self.overall_bar.setValue(0)
        self.status_label.setText("Status: Starting pipeline...")
        self.details_label.setText("Files: 0 / 0 | Bytes: 0 B | Speed: --")

    def update_scan_progress(self, current: int, total: int, filename: str):
        pct = int((current / total * 100)) if total > 0 else 0
        self.overall_bar.setValue(pct)
        self.status_label.setText(f"Status [Scanning {current}/{total}]: {filename}")
        self.details_label.setText(f"Scanned: {current} / {total} files")

    def reset_for_transfer(self, total_files: int, total_bytes: float):
        self.total_bytes = total_bytes
        gb = total_bytes / (1024 ** 3)
        self.overall_bar.setValue(0)
        self.status_label.setText(f"Status: FastCopy batch transferring {total_files} files ({gb:.2f} GB)...")
        self.details_label.setText(f"Transferred: 0.00 / {gb:.2f} GB | Speed: --")

    def update_realtime_metrics(self, metrics: dict):
        """Updates progress bars and speed label using parsed FastCopy stdout metrics."""
        bytes_trans = metrics.get("bytes_transferred")
        tot_bytes = metrics.get("total_bytes") or self.total_bytes
        pct = metrics.get("bytes_pct")
        speed = metrics.get("speed_str", "")
        current_file = metrics.get("current_file", "")

        if pct is not None:
            self.overall_bar.setValue(int(pct))

        if current_file:
            self.status_label.setText(f"Status [FastCopy]: {current_file}")

        if bytes_trans is not None and tot_bytes > 0:
            trans_gb = bytes_trans / (1024 ** 3)
            tot_gb = tot_bytes / (1024 ** 3)
            detail = f"Transferred: {trans_gb:.2f} GB / {tot_gb:.2f} GB ({pct or 0:.1f}%)"
            if speed:
                detail += f" | Speed: {speed}"
            self.details_label.setText(detail)

    def update_transfer_progress(self, copied_count: int, total_files: int, current_filename: str):
        overall_pct = int((copied_count / total_files * 100)) if total_files > 0 else 0
        self.overall_bar.setValue(overall_pct)
        self.status_label.setText(f"Status [Finalizing {copied_count}/{total_files}]: {current_filename}")
        self.details_label.setText(f"Finalized: {copied_count} / {total_files} files ({overall_pct}%)")

    def update_overall(self, current: int, total: int, status_msg: str = ""):
        self.update_scan_progress(current, total, status_msg)

    def update_details(self, files_str: str, bytes_str: str):
        self.details_label.setText(f"Files: {files_str} | Transferred: {bytes_str}")
