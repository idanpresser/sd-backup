
# MASTER PROMPT: Build `SD-FastBackup` Python Application


Act as a Principal Python and PySide6 Desktop Systems Engineer. You are tasked with building a complete, production-grade Python desktop application named "SD-FastBackup". 

This application performs ultra-fast, deduplicated, sequential SD card backups using PySide6 (Dark Theme), an embedded SQLite database, and FastCopy CLI as the underlying transfer engine.

---

### SYSTEM SPECIFICATIONS & REQUIREMENTS

#### 1. Tech Stack & Dependencies
* Python 3.10+
* PySide6 (Qt for Python)
* SQLite3 (built-in, WAL mode)
* exifread (Photo EXIF date extraction)
* pymediainfo (Video container creation date extraction)
* FastCopy CLI (Windows binary integration)

#### 2. FastCopy CLI Engine Integration
* **Executable Resolution Order:**
  1. Check relative binary path: `./bin/FastCopy.exe`
  2. Check default system installations: `C:\Program Files\FastCopy\FastCopy.exe`
  3. Fallback: Prompt/allow user selection via GUI setting input stored in `config.json`.
* **Execution Parameters:**
  The command passed to subprocess.Popen must follow this verified syntax:
  `fastcopy.exe /cmd=diff /verify /bufsize=1024 /speed=full /utf8 /auto_close /error_stop /srcfile_w="<manifest_file.txt>" /to="<destination_dir>"`

#### 3. Destination File & Folder Formatting
When copying files from source (SD Card) to destination target:
* Files must be organized dynamically based on extracted `date_taken`:
  * **Folder Structure:** `<Target_Root>/YYYY/MM/DD/`
  * **Filename Pattern:** `YYYYMMDD_HHMMSS_<original_filename>.<ext>`
  * *Example:* For a file `IMG_0001.JPG` taken on `2026-03-29 14:02:11`, the output path is:
    `<Target_Root>/2026/2026-03/2026-03-29/20260329_140211_<Suffix_From_GUI>.JPG`

#### 4. Metadata Extraction & Composite Hashing
* Extract `file_size` (bytes).
* Extract `date_taken` using this prioritized chain:
  1. EXIF Metadata (`exifread` for JPG, RAW files: `EXIF DateTimeOriginal`).
  2. Video Container Metadata (`pymediainfo` for MP4, MOV, MXF, CRM, ARI).
  3. Fallback: File modification time (`mtime`).
* **Composite Hash Formula:** `SHA256(f"{date_taken_iso}_{file_size_bytes}")`.

#### 5. Deduplication & SQLite State Catalog
* SQLite database file `.sd_backup_catalog.db` MUST be created at the root of the selected target destination directory.
* Enable WAL mode (`PRAGMA journal_mode=WAL;`).
* Tables:
  * `volumes`: Tracking scanned SD card volume serials and labels.
  * `file_catalog`: Mapping `composite_hash`, original path, target path, date taken, size, extraction method.
  * `transfer_manifest`: Log of transfer statuses (`PENDING`, `COPIED`, `FAILED`, `DUPLICATE_SKIPPED`).
* If a composite hash already exists with status `COPIED`, the file is identified as a duplicate, skipped from the FastCopy manifest, and logged to the UI Duplicate Log view.

#### 6. Resiliency, Error Handling & Alerts
* **Read Error Handling:** If a file cannot be read during scanning/hashing (e.g., bad card sector):
  * Log the error in SQLite (`FAILED`).
  * Output error details to the GUI `DEBUG` log tab.
  * Display a **non-blocking banner/toast alert** in the GUI so the user is informed without pausing the backup pipeline for remaining files.
* **Resume Engine:** If interrupted mid-copy, re-running the tool re-scans the card, ignores `COPIED` items, and re-queues incomplete/failed items.

#### 7. GUI Design & UX (PySide6)
* Modern Dark Theme stylesheet (`assets/dark_style.qss`) using dark grays (`#121212`, `#1E1E1E`), clean cyan accents (`#00ADB5`), and high contrast text (`#E0E0E0`).
* **Source Drive Selection:** Manual "Refresh Drives" button alongside a Drive Selection QComboBox.
* **Folder Targeting:** Checkboxes for `DCIM/`, `PRIVATE/`, or Full Volume root scanning.
* **Dual Progress Meters:** Overall Backup % and Current File Progress.
* **Dual Log Console (QTabWidget):**
  * **Tab 1: Duplicates Log (`INFO` level):** Shows cleanly formatted records of files skipped because they already exist in the database.
  * **Tab 2: System Trace (`DEBUG` level):** Streams real-time raw stdout from FastCopy, metadata extraction logs, and error traces.

---

### PROJECT DIRECTORY STRUCTURE TO GENERATE

Please write production-ready, modular, fully-commented Python code for the following file structure:

```text
sd_fastbackup/
│
├── main.py                     # Entry point (QApplication initialization)
├── config.json                 # Config persistence (FastCopy path, preferences)
├── requirements.txt            # Python dependencies
│
├── assets/
│   └── dark_style.qss          # Complete QSS Dark Theme
│
├── app/
│   ├── __init__.py
│   ├── main_window.py          # Primary QMainWindow & Event Wiring
│   └── components/
│       ├── drive_selector.py   # Manual Drive Refresh & Selection Widget
│       ├── progress_panel.py   # Dual Progress Bar & Speed Tracker Widget
│       ├── log_console.py      # Dual-Tab INFO/DEBUG Console Widget
│       └── alert_banner.py     # Non-blocking error notification widget
│
├── core/
│   ├── __init__.py
│   ├── worker.py               # QThread Execution Pipeline
│   ├── metadata.py             # Metadata Engine (EXIF + PyMediaInfo + Hash)
│   ├── db.py                   # SQLite Database Manager (WAL Mode)
│   ├── fastcopy.py             # FastCopy CLI Subprocess Driver
│   └── logger.py               # Custom Qt Signal Logging Handler
│
└── utils/
    ├── __init__.py
    ├── drive_detector.py       # Windows Drive Enumerator (win32api / ctypes)
    └── path_formatter.py       # YYYY/MM/DD and filename formatting logic
```

---

### INSTRUCTIONS FOR CODE GENERATION
1. Use Test Driven Development. for each phase create a branch, then write test -> RED -> implement -> GREEN -> Commit and Merge.
   Write **complete, working code** for every file listed above without placeholders, `TODO` comments, or truncated snippets.
2. Ensure `BackupWorker` derives from `QThread` and uses Qt Signals (`Signal`) to update GUI widgets safely across threads.
3. Include defensive `try/except` blocks around file operations and subprocess management.
4. Ensure target folder paths (`YYYY/MM/DD`) and renamed files (`YYYYMMDD_HHMMSS_OriginalName.ext`) are created automatically if they do not exist.

Generate the codebase now.
