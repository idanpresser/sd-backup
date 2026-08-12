# DESIGN_PLAN.md: Detailed Design & Implementation Plan

## System Name: `SD-FastBackup` (PySide6 Edition)

---

## 1. Directory & Code Base Structure

```text
sd_fastbackup/
│
├── main.py                    # Application Entry Point
├── requirements.txt           # Python Dependencies
├── README.md                  # Setup & Usage Documentation
│
├── assets/                    # Styling & Icons
│   ├── icons/                 # Application & status icons (.png/.svg)
│   └── dark_style.qss         # PySide6 Dark Theme Stylesheet
│
├── app/                       # Core GUI Layer (PySide6)
│   ├── __init__.py
│   ├── main_window.py         # Primary QMainWindow & Widget Layouts
│   ├── components/            # Reusable PySide6 Widgets
│   │   ├── card_selector.py   # Volume / Drive Selector Widget
│   │   ├── progress_panel.py  # Dual Progress Bar Component
│   │   └── log_viewer.py      # Dual-Tab Output Console (INFO / DEBUG)
│   └── styles.py              # Theme Loader & Palette Configurator
│
├── core/                      # Business & Data Logic Layer
│   ├── __init__.py
│   ├── worker.py              # QThread Backup Execution Orchestrator
│   ├── metadata.py            # Date Taken & File Size Composite Hasher
│   ├── db.py                  # SQLite Connection & Transaction Manager
│   ├── fastcopy.py            # FastCopy CLI Subprocess Driver
│   └── logger.py              # Custom Qt-Signal Logging Handler
│
└── utils/                     # Helper Utilities
    ├── __init__.py
    ├── drive_detector.py      # Cross-platform / Windows Drive Enumerator
    └── path_helpers.py        # Path Sanitizer & Subdirectory Filter
```

---

## 2. Technical Module Specifications

### 2.1 PySide6 Dark Theme (`assets/dark_style.qss`)
A professional, high-contrast dark theme engineered for clarity during field production work.

```css
/* Core Window & Dialog Dark Background */
QMainWindow, QDialog {
    background-color: #121212;
    color: #E0E0E0;
    font-family: "Segoe UI", SF Pro Display, Arial, sans-serif;
    font-size: 13px;
}

/* Containers and Group Boxes */
QGroupBox {
    border: 1px solid #2D2D2D;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    background-color: #1E1E1E;
    font-weight: bold;
    color: #00ADB5;
}

/* Buttons */
QPushButton {
    background-color: #00ADB5;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #00FFF5;
    color: #121212;
}

QPushButton:disabled {
    background-color: #333333;
    color: #666666;
}

/* Progress Bars */
QProgressBar {
    border: 1px solid #333333;
    border-radius: 4px;
    text-align: center;
    background-color: #222222;
    color: #FFFFFF;
}

QProgressBar::chunk {
    background-color: #00ADB5;
    width: 10px;
}

/* Logging Console */
QPlainTextEdit {
    background-color: #0B0B0B;
    color: #00FF66;
    font-family: "Consolas", "Courier New", monospace;
    border: 1px solid #2D2D2D;
    border-radius: 4px;
}
```

---

### 2.2 Metadata Engine & Composite Hasher (`core/metadata.py`)

Computes file identification without reading full gigabyte-sized files into RAM.

```python
import os
import hashlib
from datetime import datetime
from typing import Tuple
import exifread

class MetadataExtractor:
    """Extracts Date Taken and Size to generate a unique composite hash."""

    @staticmethod
    def get_file_size(file_path: str) -> int:
        return os.path.getsize(file_path)

    @staticmethod
    def extract_date_taken(file_path: str) -> Tuple[datetime, str]:
        """
        Attempts extraction via:
        1. Photo EXIF (DateTimeOriginal)
        2. Fallback to Filesystem mtime
        """
        try:
            if file_path.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff', '.cr2', '.cr3', '.nef', '.arw')):
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f, stop_tag='EXIF DateTimeOriginal', details=False)
                    if 'EXIF DateTimeOriginal' in tags:
                        date_str = str(tags['EXIF DateTimeOriginal'])
                        dt = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                        return dt, "EXIF"
        except Exception:
            pass # Fall through to mtime fallback

        # Fallback to filesystem mtime
        mtime = os.path.getmtime(file_path)
        dt = datetime.fromtimestamp(mtime)
        return dt, "MTIME"

    @classmethod
    def compute_composite_hash(cls, file_path: str) -> Tuple[str, int, datetime, str]:
        """
        Generates SHA256 string from string concatenation: 'YYYY-MM-DDTHH:MM:SS_BYTES'
        Returns: (hash_str, size_bytes, date_taken, source_type)
        """
        size = cls.get_file_size(file_path)
        date_taken, source = cls.extract_date_taken(file_path)
        
        iso_date = date_taken.strftime("%Y-%m-%dT%H:%M:%S")
        raw_key = f"{iso_date}_{size}"
        
        composite_hash = hashlib.sha256(raw_key.encode('utf-8')).hexdigest()
        return composite_hash, size, date_taken, source
```

---

### 2.3 SQLite Database Manager (`core/db.py`)

Handles atomic operations, state persistence, and duplicate checks.

```python
import sqlite3
import os
from typing import Optional, List, Dict, Any

class DatabaseManager:
    """Thread-safe SQLite Manager operating on the target backup directory."""

    def __init__(self, target_dir: str):
        self.db_path = os.path.join(target_dir, ".sd_backup_catalog.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS volumes (
                    volume_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    volume_serial TEXT UNIQUE,
                    volume_label TEXT,
                    last_scanned_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS file_catalog (
                    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_hash TEXT UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    date_taken DATETIME NOT NULL,
                    date_taken_source TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transfer_manifest (
                    transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_hash TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    copy_status TEXT CHECK(copy_status IN ('PENDING', 'COPIED', 'FAILED', 'DUPLICATE_SKIPPED')),
                    transferred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(composite_hash) REFERENCES file_catalog(composite_hash)
                );
            """)

    def is_file_copied(self, composite_hash: str) -> bool:
        """Returns True if the file hash is marked as COPIED in the target database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM transfer_manifest 
                WHERE composite_hash = ? AND copy_status = 'COPIED' 
                LIMIT 1
            """, (composite_hash,))
            return cursor.fetchone() is not None

    def register_file(self, composite_hash: str, filename: str, rel_path: str, size: int, dt: str, source: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO file_catalog (composite_hash, original_filename, relative_path, file_size_bytes, date_taken, date_taken_source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(composite_hash) DO NOTHING
            """, (composite_hash, filename, rel_path, size, dt, source))

    def update_transfer_status(self, composite_hash: str, source: str, dest: str, status: str):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO transfer_manifest (composite_hash, source_path, destination_path, copy_status)
                VALUES (?, ?, ?, ?)
            """, (composite_hash, source, dest, status))
```

---

### 2.4 FastCopy Driver Integration (`core/fastcopy.py`)

Interface for spawner, job file list creation, and process management.

```python
import subprocess
import os
import tempfile
from typing import List, Generator

class FastCopyRunner:
    """Wraps FastCopy executable for high-speed file transfers."""

    def __init__(self, fastcopy_executable_path: str):
        self.exe_path = fastcopy_executable_path
        if not os.path.exists(self.exe_path):
            raise FileNotFoundError(f"FastCopy executable not found at: {self.exe_path}")

    def execute_manifest_copy(self, source_files: List[str], target_dir: str) -> Generator[str, None, int]:
        """
        Creates a temporary file list and spawns FastCopy.
        Yields STDOUT lines for UI progress updates.
        Returns FastCopy exit code.
        """
        # Create temporary filelist for FastCopy
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt', encoding='utf-8') as temp_manifest:
            manifest_path = temp_manifest.name
            for path in source_files:
                temp_manifest.write(f"{path}\n")

        cmd = [
            self.exe_path,
            "/cmd=diff",
            f"/filelist={manifest_path}",
            f"/to={target_dir}",
            "/bufsize=1024",
            "/verify",
            "/auto_close"
        ]

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            for line in process.stdout:
                yield line.strip()

            process.wait()
            return process.returncode
        finally:
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
```

---

### 2.5 Multi-Threaded Backup Worker (`core/worker.py`)

Executes the backup loop asynchronously without stalling the Qt UI.

```python
import os
from PySide6.QtCore import QThread, Signal, QObject
from core.metadata import MetadataExtractor
from core.db import DatabaseManager
from core.fastcopy import FastCopyRunner
import logging

class WorkerSignals(QObject):
    scan_started = Signal(str)
    scan_progress = Signal(int, int, str)
    duplicate_found = Signal(str, str, int)  # file_name, hash, size
    transfer_started = Signal(int, int)      # total_files, total_bytes
    transfer_line = Signal(str)
    finished = Signal(dict)
    error = Signal(str)

class BackupWorker(QThread):
    def __init__(self, source_card_path: str, target_dir: str, fastcopy_path: str):
        super().__init__()
        self.source_path = source_card_path
        self.target_dir = target_dir
        self.fastcopy_path = fastcopy_path
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def run(self):
        try:
            db = DatabaseManager(self.target_dir)
            fastcopy = FastCopyRunner(self.fastcopy_path)

            # 1. Discover target media directory (prefer DCIM)
            dcim_path = os.path.join(self.source_path, "DCIM")
            scan_root = dcim_path if os.path.exists(dcim_path) else self.source_path

            self.signals.scan_started.emit(scan_root)

            # Gather files
            all_files = []
            for root, _, files in os.walk(scan_root):
                for f in files:
                    if not f.startswith('.'):
                        all_files.append(os.path.join(root, f))

            total_files = len(all_files)
            files_to_copy = []
            total_copy_bytes = 0
            duplicate_count = 0

            # 2. Scanning & Deduplication Phase
            for idx, file_path in enumerate(all_files, start=1):
                if self._is_cancelled:
                    return

                h_val, size, dt, source = MetadataExtractor.compute_composite_hash(file_path)
                rel_path = os.path.relpath(file_path, self.source_path)

                # Register in database catalog
                db.register_file(h_val, os.path.basename(file_path), rel_path, size, dt.isoformat(), source)

                # Deduplication query
                if db.is_file_copied(h_val):
                    duplicate_count += 1
                    # Emit INFO duplicate signal
                    self.signals.duplicate_found.emit(os.path.basename(file_path), h_val, size)
                    db.update_transfer_status(h_val, file_path, os.path.join(self.target_dir, os.path.basename(file_path)), 'DUPLICATE_SKIPPED')
                else:
                    files_to_copy.append((file_path, h_val))
                    total_copy_bytes += size

                self.signals.scan_progress.emit(idx, total_files, os.path.basename(file_path))

            # 3. FastCopy Execution Phase
            if files_to_copy:
                self.signals.transfer_started.emit(len(files_to_copy), total_copy_bytes)
                source_paths = [item[0] for item in files_to_copy]

                # Run FastCopy & stream updates
                exit_code = 0
                for output_line in fastcopy.execute_manifest_copy(source_paths, self.target_dir):
                    if self._is_cancelled:
                        return
                    self.signals.transfer_line.emit(output_line)

                # Flag successful transfers in DB
                for src_path, h_val in files_to_copy:
                    dest_path = os.path.join(self.target_dir, os.path.basename(src_path))
                    db.update_transfer_status(h_val, src_path, dest_path, 'COPIED')

            summary = {
                'scanned': total_files,
                'duplicates': duplicate_count,
                'copied': len(files_to_copy),
                'bytes': total_copy_bytes
            }
            self.signals.finished.emit(summary)

        except Exception as e:
            logging.exception("Fatal error during backup pipeline execution.")
            self.signals.error.emit(str(e))

    def cancel(self):
        self._is_cancelled = True
```

---

## 3. Implementation Sequence & Milestones

```text
Phase 1: Foundation (Core Subsystems)
├── Step 1.1: Database Schema & Migration setup (`core/db.py`)
├── Step 1.2: Metadata Engine & Composite Hasher (`core/metadata.py`)
└── Step 1.3: FastCopy CLI subprocess execution layer (`core/fastcopy.py`)

Phase 2: GUI & Threading Integration
├── Step 2.1: PySide6 QSS Dark Stylesheet setup (`assets/dark_style.qss`)
├── Step 2.2: Dual Logging Handler routing (`core/logger.py`)
├── Step 2.3: `BackupWorker(QThread)` Orchestrator wiring (`core/worker.py`)
└── Step 2.4: Primary Window UI construction (`app/main_window.py`)

Phase 3: Testing & Hardening
├── Step 3.1: Resume execution validation on interrupted transfers
├── Step 3.2: Duplicate recognition test suite (re-inserting same SD card)
└── Step 3.3: Missing FastCopy binary handling & SD pullout edge case tests
```

---

## 4. Execution Entry Point (`main.py`)

```python
import sys
import os
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    
    # Load stylesheet
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "dark_style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
```

---

## 5. Summary & Hand-off

This completes the architectural specification and implementation design for `SD-FastBackup`.

* **PRD.md:** Product requirements, user stories, and features.
* **ARCHITECTURE.md:** High-level component diagrams, SQLite schema, PySide6 signals layout, and system boundaries.
* **DESIGN_PLAN.md:** File structures, Dark Theme QSS, core classes implementation (`MetadataExtractor`, `DatabaseManager`, `FastCopyRunner`, `BackupWorker`), and development roadmap.