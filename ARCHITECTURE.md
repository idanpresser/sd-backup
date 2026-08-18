# ARCHITECTURE.md: System Architecture Document

## System Name: `SD-FastBackup` (PySide6 Graphical Edition)

---

## 1. High-Level Architecture Overview

`SD-FastBackup` is structured using a decoupled **Model-View-Controller (MVC) / Worker Pattern** tailored for GUI applications with intensive disk I/O. 

The application uses **PySide6 (Qt for Python)** for a modern, dark-themed user interface, coupled with an asynchronous worker pipeline executing on separate threads to keep the UI responsive. Data transfer is delegated to **FastCopy CLI**, and internal state/deduplication registry is managed by an embedded **SQLite3** database placed on the target backup drive.

```
+-----------------------------------------------------------------------------------+
|                                 PYSIDE6 GUI LAYER                                 |
|  +-----------------------+  +------------------------+  +----------------------+  |
|  | Card Selection / Status|  | Backup Control / Progress|  | Real-Time Duplicate Log |  |
|  |     (QComboBox/List)  |  |   (QProgressBar/Labels)|  |  (QPlainTextEdit INFO)|  |
|  +-----------------------+  +------------------------+  +----------------------+  |
+------------------------------------------|----------------------------------------+
                                           | Qt Signals / Slots
                                           v
+-----------------------------------------------------------------------------------+
|                              BACKUP ORCHESTRATOR LAYER                            |
|                                (BackupWorker : QThread)                           |
+--------------------|---------------------|----------------------|-----------------+
                     |                     |                      |
                     v                     v                      v
+------------------------+  +--------------------+  +-------------------------------+
| METADATA & HASH ENGINE |  | SQLITE STATE STORE |  | FASTCOPY SUBPROCESS WRAPPER   |
| (ExifRead / Size Hash) |  | (WAL Mode / Index) |  | (FastCopy.exe Async Execution)|
+------------------------+  +--------------------+  +-------------------------------+
```

---

## 2. Layer & Component Specification

### 2.1 UI Layer (`ui/`)
* **Technology:** PySide6 (Qt 6 for Python), custom dark QSS / Palette.
* **Responsibilities:**
  * Render card discovery, volume details, transfer progress, duplicate counts, and transfer speed.
  * Receive background status updates via Qt **Signals/Slots** (`sig_progress`, `sig_duplicate_found`, `sig_error`, `sig_card_completed`).
  * Display dedicated tabs/drawers for **INFO Duplicate Logs** and raw **DEBUG System Logs**.
  * Facilitate batch/sequential SD card swaps without restarting the GUI.

### 2.2 Orchestrator & Worker Layer (`core/worker.py`)
* **Technology:** PySide6 `QThread` / `QRunnable`.
* **Responsibilities:**
  * Prevent UI freeze by offloading volume scanning, metadata parsing, SQLite queries, and subprocess lifecycle management.
  * Orchestrate execution sequence: `Scan` -> `Hash` -> `Filter Duplicates` -> `Generate Manifest` -> `Spawn FastCopy` -> `Update SQLite DB`.

### 2.3 Metadata Engine (`core/metadata.py`)
* **Technology:** `exifread` (Photos), `pymediainfo` or structural header parsing (Videos), `os.stat`.
* **Responsibilities:**
  * Extract `Date Taken` (EXIF `DateTimeOriginal`, QuickTime `creation_time`, or fallback to OS `mtime`).
  * Extract exact file size in bytes.
  * Compute the unique **Composite Hash**: `SHA256(DateTaken_Bytes)`.

### 2.4 Database & Persistence Layer (`core/db.py`)
* **Technology:** SQLite3 (WAL mode enabled for multi-thread safety).
* **Responsibilities:**
  * Maintain table schemas for `scanned_cards`, `backed_up_files`, and `transfer_sessions`.
  * Execute duplicate checks before issuing file copy operations.
  * Provide atomic status updates (`PENDING`, `IN_PROGRESS`, `COPIED`, `FAILED`).

### 2.5 Transfer Subsystem (`core/fastcopy.py`)
* **Technology:** Windows Process API via Python `subprocess.Popen` / `QProcess`.
* **Responsibilities:**
  * Build CLI command sequences for `FastCopy.exe`.
  * Stream FastCopy standard output / status logs.
  * Handle non-zero exit codes, card disconnect errors, and process termination requests.

### 2.6 Dual-Channel Logging System (`core/logger.py`)
* **Technology:** Standard library `logging` + custom Qt `QObject` signal handler (`QtLogHandler`).
* **Responsibilities:**
  * **File Logging (`DEBUG`):** Pipe full execution details, system calls, FastCopy CLI args, and stack traces to `.sd_backup_logs/app_debug.log`.
  * **UI Logging (`INFO`):** Intercept duplicate file hits and user-facing lifecycle events, routing them directly to the PySide6 UI Duplicate Log panel.

---

## 3. Database Schema Design (SQLite)

The SQLite database `.sd_backup_catalog.db` is stored at the root of the selected **Backup Target Directory**.

```sql
-- Volumes Table: Tracks each processed SD Card
CREATE TABLE IF NOT EXISTS volumes (
    volume_id INTEGER PRIMARY KEY AUTOINCREMENT,
    volume_label TEXT,
    volume_serial TEXT UNIQUE,
    total_capacity_bytes INTEGER,
    first_seen_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_scanned_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Files Catalog: Stores file composite hashes, source & target filenames, and duplicate tracking states
CREATE TABLE IF NOT EXISTS file_catalog (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    composite_hash TEXT UNIQUE NOT NULL, -- SHA256(date_taken + size_bytes)
    original_filename TEXT NOT NULL,     -- Pristine camera source filename (e.g. IMG_0001.JPG)
    relative_path TEXT NOT NULL,        -- Source relative path inside DCIM/Media folder
    destination_filename TEXT,          -- Renamed target filename (e.g. 20260811_150626_Suffix_0001.JPG)
    target_relative_path TEXT,          -- Destination relative path in backup structure
    file_size_bytes INTEGER NOT NULL,
    date_taken DATETIME NOT NULL,
    date_taken_source TEXT NOT NULL      -- 'EXIF', 'CONTAINER', 'MTIME'
);

CREATE INDEX IF NOT EXISTS idx_composite_hash ON file_catalog(composite_hash);

-- Backup Log Table: Tracks copy execution histories and verification
CREATE TABLE IF NOT EXISTS transfer_manifest (
    transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    composite_hash TEXT NOT NULL,
    source_absolute_path TEXT NOT NULL,
    destination_absolute_path TEXT NOT NULL,
    copy_status TEXT CHECK(copy_status IN ('PENDING', 'IN_PROGRESS', 'COPIED', 'FAILED', 'DUPLICATE_SKIPPED')),
    fastcopy_exit_code INTEGER,
    error_message TEXT,
    transferred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(composite_hash) REFERENCES file_catalog(composite_hash)
);
```

---

## 4. Multi-Threading & Signal Architecture

To ensure high performance and an ultra-responsive UI, all scanning and I/O tasks execute off the main thread.

```
       +-------------------+
       |   PySide6 Main    |
       |    GUI Thread     |
       +---------+---------+
                 |
                 | 1. User clicks "Start Backup"
                 v
       +-------------------+
       |  BackupWorker     | <--- Runs in QThread
       |  (Thread Pool)    |
       +---------+---------+
                 |
  +--------------+--------------+-------------------+
  | 2. Extract Metadata & Hash  | 3. Query DB       | 4. Launch FastCopy
  v                             v                   v
+-------------------+  +-------------------+  +-------------------+
|  MetadataEngine   |  |   DatabaseManager |  | FastCopyWrapper   |
+-------------------+  +-------------------+  +-------------------+
  |                             |                   |
  +--------------+--------------+-------------------+
                 |
                 | 5. Emit Signals (Progress, Duplicate Found, Logs)
                 v
       +-------------------+
       | PySide6 GUI UI    | (Renders updates on main thread safely)
       +-------------------+
```

### Signal Specifications (`WorkerSignals(QObject)`)
* `sig_scan_started(str volume_label)`
* `sig_scan_progress(int current, int total, str current_file)`
* `sig_duplicate_detected(dict file_info)` -> Routes to UI Duplicate Panel (`INFO`)
* `sig_transfer_started(int total_files, int total_bytes)`
* `sig_transfer_progress(int files_copied, int bytes_copied, float speed_mbps)`
* `sig_log_debug(str message)` -> Writes to `DEBUG` log tab/file
* `sig_card_completed(dict summary)`
* `sig_error(str title, str detail)`

---

## 5. UI Layout Structure (Dark Theme PySide6)

The GUI utilizes a sleek, dark dashboard pattern modeled after professional media offloading suites (e.g., Silverstack, Hedge).

```
+-----------------------------------------------------------------------------------+
|  SD-FastBackup v1.0 [Dark Mode]                     [ Settings ] [ FastCopy Path ]|
+-----------------------------------------------------------------------------------+
| SOURCE SD CARD                               | BACKUP TARGET DESTINATION          |
| [ E:\ (EOS_DIGITAL - 128 GB)          |V| ]  | [ D:/Backups/2026_03_Shoot   [Browse] ]|
+----------------------------------------------+------------------------------------+
| TARGET FOLDERS TO SCAN                       | DISCOVERY & DEDUPLICATION SUMMARY  |
| [x] DCIM/  [x] PRIVATE/  [ ] Full Drive      | Total Scanned: 1,420 files (84 GB) |
|                                              | Duplicates Identified: 320 (12 GB) |
|                                              | Files Queued: 1,100 files (72 GB)  |
+----------------------------------------------+------------------------------------+
| TRANSFER PROGRESS                                                                 |
| Overall: [============================================...........] 68%            |
| Status:  Copying IMG_4821.CR3 (45 MB/s) - FastCopy Active                         |
+-----------------------------------------------------------------------------------+
| LOG TABS: [ Duplicates Log (INFO) ]  [ System Trace (DEBUG) ]                     |
| +-------------------------------------------------------------------------------+ |
| | [14:02:11][INFO] DUPLICATE SKIPPED: DCIM/100CANON/IMG_0012.CR3                | |
| |        Reason: Matched Hash [3f91a2...] (Already backed up on 2026-03-29)     | |
| | [14:02:11][INFO] DUPLICATE SKIPPED: DCIM/100CANON/IMG_0013.CR3                | |
| +-------------------------------------------------------------------------------+ |
+-----------------------------------------------------------------------------------+
| [ START BACKUP QUEUE ]  [ EJECT & NEXT CARD ]                    [ CANCEL/PAUSE ] |
+-----------------------------------------------------------------------------------+
```

---

## 6. FastCopy Integration Mechanics

1. **Manifest File Generation:** Rather than exceeding OS command-line argument limits with thousands of file paths, the worker creates a temporary job list file (`manifest_job.txt`).
2. **Execution Invocation:**
   ```bash
   FastCopy.exe /cmd=diff /filelist="manifest_job.txt" /to="D:\Backups\2026_03_Shoot\" /bufsize=1024 /verify /postproc=NULL /auto_close
   ```
3. **Progress Parsing:** FastCopy’s STDOUT is captured line-by-line via pipe in real-time to update progress meters.
4. **Verification & Commit:** Only files with FastCopy return status `0` (Success) will have their state updated to `COPIED` in the SQLite database.

---

## 7. Resume & Error Recovery Workflow

```
[Crash/Disconnect Triggered]
            │
            ▼
[App Restarts & Re-scans SD Card]
            │
            ▼
[Scan Files & Extract Hashes]
            │
            ▼
[Check SQLite DB for Composite Hashes]
     ├── Hash Exists & Status == 'COPIED' -> SKIP (Log to Duplicate Panel)
     ├── Hash Exists & Status == 'IN_PROGRESS' / 'FAILED' -> QUEUE FOR RETRY
     └── Hash Does Not Exist -> QUEUE FOR COPY
            │
            ▼
[FastCopy Executed Only For Unfinished/New Files]
            │
            ▼
[Atomic DB Commit On Success]
```

---

*I am ready to generate the final detailed implementation design document (`DESIGN_PLAN.md`). Please prompt **CONTINUE** to proceed.*