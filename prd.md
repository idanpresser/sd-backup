# PRD.md: Product Requirements Document

## Product Name: `SD-FastBackup`
**Version:** 1.0.0  
**Author:** System Architecture Team  
**Status:** Draft / Approved for Design  

---

## 1. Executive Summary
`SD-FastBackup` is a high-speed, automated Python CLI application designed for photographers, videographers, and digital media professionals who need to offload multiple SD cards sequentially after a shoot. By pairing Python’s file orchestration with the raw transfer speed of **FastCopy** (Windows) / native high-speed engine interfaces, an **SQLite** tracking database, and smart composite hashing (Date Taken + File Size), the application guarantees rapid, zero-duplicate, and resumable backups across multiple cards.

---

## 2. Problem Statement & Objectives

### 2.1 Problem Statement
* Offloading multiple 128GB–512GB SD cards manually is slow, error-prone, and prone to duplicate creation.
* Standard OS copy routines lack robust retry/resume mechanics for interrupted transfers.
* Cryptographic hashing (MD5/SHA256) of multi-terabyte raw video files (4K/8K) takes longer than the transfer itself.
* Photographers frequently reuse media across cards or re-insert previously backed-up cards, wasting disk space and transfer time.

### 2.2 Product Objectives
* **Ultra-Fast Ingestion:** Use FastCopy as the underlying transfer engine for maximum I/O throughput.
* **Lightweight Smart Deduplication:** Compute a composite unique identifier based on `[Date Taken] + [File Size]` to identify identical files without full content hashing.
* **Smart Folder Filtering:** Isolate and ingest media from photo/video directories (primarily `DCIM` and standard camera structures like `PRIVATE/AVCHD`).
* **Sequential Workflow:** Support sequential SD card processing—eject card 1, insert card 2, resume/continue seamlessly.
* **Resiliency & Resume:** Maintain a persistent SQLite state database so interrupted transfers can resume exactly where they stopped without corrupting destination storage.
* **Differentiated Logging:** Provide granular debugging details (`DEBUG`) while isolating duplicate reporting to standard output (`INFO`).

---

## 3. Scope & Target Target Platform

### 3.1 OS & Platform Targets
* **Primary OS:** Windows 10 / 11 (optimized for FastCopy CLI integration `FastCopy.exe`).
* **Runtime:** Python 3.10+
* **Dependencies:** SQLite3 (built-in), `exifread` / `Pillow` / `pymediainfo` (for metadata parsing), FastCopy standalone binary.

### 3.2 In Scope
* Automatic detection and folder targeting (targeting `DCIM`, `PRIVATE`, or user-specified media paths).
* Persistent tracking via an SQLite database placed in the backup destination directory.
* Composite hash generation (`date_taken` + `file_size`).
* Deduplication verification prior to passing transfer manifests to FastCopy.
* Interactive CLI prompt workflow for sequential multi-card offloading.
* High-verbosity log files and low-verbosity duplicate summaries on console.

### 3.3 Out of Scope
* Automatic destructive formatting of SD cards after backup (safety first).
* Cloud storage syncing (local storage targets only).
* GUI front-end (v1.0 is CLI/TUI focused).

---

## 4. User Personas & Workflows

### 4.1 Target User: The Field Media Manager / Photographer
* Needs to dump 5 to 10 SD cards sequentially into a main field drive (e.g., Rugged SSD / RAID array).
* Wants to know immediately if a file was already backed up from a previous session or another card.
* Cannot afford dropped frames, partial transfers, or silent file corruptions.

### 4.2 Sequential Standard Workflow
```
[Start App] 
    └──> Select Destination Directory (Database initialized/loaded)
    └──> Loop:
          ├──> Detect / Select SD Card Drive Letter (e.g., E:\)
          ├──> Scan Target Paths (DCIM / Media Folders)
          ├──> Extract Metadata (Size + Date Taken) -> Generate Composite Hash
          ├──> Check SQLite DB -> Filter out Existing Duplicates
          ├──> Execute FastCopy for New/Updated Files
          ├──> Commit Transferred State to SQLite DB
          └──> Prompt: "Insert Next SD Card or (Q)uit?"
```

---

## 5. Functional Requirements

### FR-1: Directory Scanning & Targeting
* **FR-1.1:** The app shall search the root of the designated SD card for `DCIM` directory and standard video structures (`PRIVATE`, `MP_ROOT`).
* **FR-1.2:** If no standard media folders exist, the app shall offer an option to scan the full volume root or cancel.
* **FR-1.3:** The app shall ignore OS system junk files (e.g., `.DS_Store`, `System Volume Information`, `IndexerVolumeGuid`).

### FR-2: Composite Hash Generation (`Date Taken` + `Size`)
* **FR-2.1:** For every discovered media file, the app shall extract the `file_size` (in bytes).
* **FR-2.2:** The app shall extract the `date_taken` timestamp using:
  1. EXIF metadata (Photos: `EXIF DateTimeOriginal`).
  2. Container metadata (Videos: QuickTime/MP4 creation time).
  3. Fallback: OS File Modification Time (`mtime`) if metadata tags are absent or unreadable.
* **FR-2.3:** The composite hash string shall be calculated as `SHA256(f"{date_taken_iso}_{file_size_bytes}")`.

### FR-3: SQLite State Storage & Schema
* **FR-3.1:** The SQLite database file (`.sd_backup_catalog.db`) shall reside at the root of the target destination directory.
* **FR-3.2:** The database must track:
  * **Volumes:** Volume Serial Number, Label, First/Last Scanned Timestamp.
  * **Files:** Composite Hash, Original Filename, Source Relative Path, Destination Relative Path, File Size, Date Taken, Backup Status (`PENDING`, `COPIED`, `FAILED`), FastCopy Exit Code, Checksum Verification status.

### FR-4: Deduplication Logic
* **FR-4.1:** Prior to copy, the app shall query the SQLite database using the generated composite hash.
* **FR-4.2:** If a record exists with status `COPIED` and destination file size matches:
  * Mark file as `DUPLICATE`.
  * Bypass FastCopy execution for this file.
  * Log duplicate detail to `INFO` log level.
* **FR-4.3:** If a composite hash exists but destination file is missing/corrupted, mark status as `RETRY` and queue for copy.

### FR-5: FastCopy Engine Execution
* **FR-5.1:** The app shall construct dynamic job lists or leverage FastCopy command-line arguments (`FastCopy.exe`).
* **FR-5.2:** FastCopy options shall be configured for maximum reliability and speed:
  * `/cmd=diff` (or list file input)
  * `/verify` (enable hardware/hash verify where applicable)
  * `/bufsize=1024` (or user-configurable mega-bytes buffer)
  * `/auto_close`
  * `/log=FALSE` (logging delegated to Python logging service)
* **FR-5.3:** The app shall parse FastCopy process return codes and stdout to confirm successful delivery.

### FR-6: Interruption, Retry & Resume Mechanics
* **FR-6.1:** Transfers shall be batched or tracked transactional-wise in SQLite.
* **FR-6.2:** If a process is terminated mid-transfer (e.g., CTRL+C or card disconnect):
  * Unfinished transfers remain flagged as `PENDING` or `FAILED`.
  * Upon re-running the tool on the same card, the application will re-evaluate pending/failed items and re-submit them to FastCopy.

### FR-7: Logging Architecture
* **FR-7.1 Logging Levels:**
  * `DEBUG`: Detailed execution trace, metadata extraction details, raw FastCopy CLI commands, stdout/stderr streams, timing diagnostics.
  * `INFO`: Clean sequential operational outputs, summary statistics (total bytes transferred, total files scanned), and **explicit duplicate listings**.
* **FR-7.2 File and Console Targets:**
  * Log File: Full `DEBUG` logs written to `.sd_backup_logs/backup_YYYYMMDD_HHMMSS.log` on destination drive.
  * Console Output: Filtered `INFO` messages + interactive UI prompts.

---

## 6. Non-Functional Requirements

* **Performance:** Processing 1,000 metadata entries (size + date taken) must complete in under 5 seconds. Offloading speed must equal or exceed FastCopy standalone capabilities (saturating bus/card speed limits, e.g., 300MB/s–1000MB/s).
* **Reliability:** Data integrity is paramount. No source files shall ever be modified or deleted.
* **Robustness:** Gracefully handle card disconnects mid-scan or mid-copy without corrupting the SQLite catalog.
* **Portability:** Self-contained executable or cleanly packaged Python module with minimal external dependencies.

---

## 7. Edge Case Requirements & Error Handling

| Edge Case | Expected System Behavior |
| :--- | :--- |
| **No EXIF/Video Metadata** | System falls back to filesystem `mtime` / `ctime`. Logs warning in `DEBUG`. |
| **Identical Files, Different Names** | Composite hash matches (`date_taken` + `size`); identified as duplicate and skipped. |
| **Different Files, Same Name** | Composite hash differs; file is copied and appended with unique collision suffix in target if needed. |
| **Card Ejected Mid-Transfer** | FastCopy process fails -> Exception caught -> File flagged as `FAILED` in SQLite -> System alerts user without crashing. |
| **FastCopy Executable Not Found** | System halts gracefully with instructions to provide `--fastcopy-path` or install binary. |

---

*I am ready to proceed to the next document (`ARCHITECTURE.md`). Please prompt **CONTINUE** to generate it.*