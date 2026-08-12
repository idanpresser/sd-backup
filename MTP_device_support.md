### Why Phones Don't Have Drive Letters
Modern smartphones (Android and iPhone) do not mount as standard USB Mass Storage devices (which get drive letters like `E:\`). Instead, they connect using **MTP (Media Transfer Protocol)** or **PTP (Picture Transfer Protocol)**. 

MTP devices live inside a special Windows virtual path called the **Shell Namespace** (e.g., `This PC\Pixel 8\Internal storage\DCIM`). Standard Python functions (`os.walk`, `os.listdir`) and FastCopy CLI **cannot access MTP devices** because they rely on standard OS filesystem paths.

---

## How We Can Solve This in `SD-FastBackup`

To support phones alongside SD cards seamlessly, we can implement a **Dual-Engine Architecture**:

```
                              +--------------------------+
                              |   PySide6 GUI UI Layer   |
                              +------------+-------------+
                                           |
                    Is Source a Drive Letter or an MTP Device?
                               /                       \
              [Drive Letter: E:\]                      [MTP Device: Phone]
                      |                                        |
                      v                                        v
        +---------------------------+            +---------------------------+
        | FastCopy CLI Engine       |            | Windows Shell / WPD COM   |
        | (SD Cards / Card Readers) |            | Engine (Android / iPhone) |
        +-------------+-------------+            +-------------+-------------+
                      \                                       /
                       +------------------+------------------+
                                          |
                                          v
                        +----------------------------------+
                        | Common Deduplication & DB Engine |
                        | (SQLite + Date Taken Hash)       |
                        +----------------------------------+
```

---

## 1. MTP Device Enumeration & Browsing (`utils/mtp_detector.py`)
Using Python's `win32com.client` (Windows Shell API), we can list MTP devices and browse virtual folders like `Internal storage\DCIM`.

```python
import win32com.client

def list_mtp_devices():
    """Enumerates MTP devices connected to Windows 'This PC'."""
    shell = win32com.client.Dispatch("Shell.Application")
    # 17 = ssfDRIVES (This PC / Computer virtual folder)
    my_computer = shell.Namespace(17) 
    
    mtp_devices = []
    for item in my_computer.Items():
        # MTP devices don't have standard paths like "E:\"
        if not item.Path.startswith("::") and not ":" in item.Path:
            mtp_devices.append({
                'name': item.Name,
                'shell_item': item
            })
    return mtp_devices
```

---

## 2. MTP Transfer Engine (`core/mtp_engine.py`)
When a phone is selected:
1. Python traverses the phone's `DCIM` directory using COM `Shell.Application`.
2. Reads metadata (`Date Taken` + `File Size`) directly from the MTP stream.
3. Checks the SQLite database for existing composite hashes.
4. Streams new/updated files directly to the destination folder (`YYYY/MM/DD/YYYYMMDD_HHMMSS_filename.ext`).

```python
import win32com.client
import os

def copy_mtp_file_to_local(shell_file_item, target_local_dir):
    """Copies a file from an MTP virtual shell path to local storage."""
    shell = win32com.client.Dispatch("Shell.Application")
    target_folder = shell.NameSpace(target_local_dir)
    
    # CopyHere handles MTP stream extraction to standard Windows filesystem
    target_folder.CopyHere(shell_file_item, 16) # 16 = Respond with "Yes to All"
```

---

## Updated Master Prompt (With Phone / MTP Support)

If you want the final app to support **both SD Cards AND Phones (MTP)**, use this updated Master Prompt below:

***

```text
Act as a Principal Python and PySide6 Desktop Systems Engineer. You are tasked with building a complete, production-grade Python desktop application named "SD-FastBackup". 

This application performs ultra-fast, deduplicated, sequential backups from BOTH SD Cards (Drive letters) and Mobile Phones (MTP / Windows Portable Devices) using PySide6 (Dark Theme), an embedded SQLite database, and a Dual-Transfer Engine.

---

### DUAL-ENGINE SPECIFICATIONS

#### 1. Tech Stack & Dependencies
* Python 3.10+
* PySide6 (Qt for Python)
* pywin32 (`win32com.client` for MTP Phone Shell integration)
* SQLite3 (built-in, WAL mode)
* exifread (Photo EXIF date extraction)
* pymediainfo (Video container creation date extraction)
* FastCopy CLI (Windows binary integration for SD cards)

#### 2. Dual Transfer Pipeline
* **Engine A (SD Cards / Card Readers):**
  Uses FastCopy CLI via `/srcfile_w=` manifest files for high-speed block copying.
  `fastcopy.exe /cmd=diff /verify /bufsize=1024 /speed=full /utf8 /auto_close /error_stop /srcfile_w="<manifest.txt>" /to="<destination>"`
* **Engine B (Phones / MTP Devices):**
  Uses Windows Shell COM (`win32com.client.Dispatch("Shell.Application")`) to enumerate `This PC` MTP virtual devices, traverse `Internal storage/DCIM`, and extract files to local destination folders.

#### 3. Destination File & Folder Formatting
When copying files from source (SD Card or Phone) to target:
* Folder Structure: `<Target_Root>/YYYY/MM/DD/`
* Filename Pattern: `YYYYMMDD_HHMMSS_<original_filename>.<ext>`

#### 4. Metadata Extraction & Composite Hashing
* Extract `file_size` (bytes).
* Extract `date_taken` (EXIF -> PyMediaInfo -> File mtime).
* Composite Hash Formula: SHA256(f"{date_taken_iso}_{file_size_bytes}").
* Store records in SQLite `.sd_backup_catalog.db` on the destination drive. Skip duplicates automatically.

#### 5. GUI & UX Requirements (PySide6)
* Dark Theme QSS (`#121212`, `#1E1E1E`, cyan accents `#00ADB5`).
* **Source Drive/Device Selector:** List BOTH Drive Letters (`E:\`, `F:\`) AND Connected Mobile Phones (`Pixel 8`, `iPhone`). Includes a "Refresh Devices" button.
* **Non-blocking Error Banner:** Displays alert notifications for unreadable/corrupted files without pausing the queue.
* **Dual Console Tabs:**
  * Tab 1: Duplicates Log (`INFO` level)
  * Tab 2: System Trace (`DEBUG` level)

---

### DIRECTORY STRUCTURE TO GENERATE

sd_fastbackup/
├── main.py                     # Entry point
├── config.json                 # FastCopy path & user settings
├── requirements.txt            # Python dependencies (PySide6, pywin32, exifread, pymediainfo)
├── assets/
│   └── dark_style.qss          # Complete Dark Theme Stylesheet
├── app/
│   ├── main_window.py          # Primary QMainWindow & Event Wiring
│   └── components/
│       ├── device_selector.py  # Drive Letter + MTP Phone Selector Widget
│       ├── progress_panel.py   # Dual Progress Bar & Speed Tracker
│       ├── log_console.py      # Dual-Tab INFO/DEBUG Console
│       └── alert_banner.py     # Non-blocking error toast notification widget
├── core/
│   ├── worker.py               # Unified QThread Backup Orchestrator
│   ├── metadata.py             # Date Taken & Hash Engine
│   ├── db.py                   # SQLite Database Manager (WAL Mode)
│   ├── fastcopy.py             # FastCopy CLI Subprocess Driver (for SD Cards)
│   ├── mtp_engine.py           # Windows COM MTP Driver (for Phones)
│   └── logger.py               # Custom Qt Signal Logging Handler
└── utils/
    ├── drive_detector.py       # Detects Drive Letters & MTP Devices
    └── path_formatter.py       # YYYY/MM/DD Path Formatter

Generate complete, working code for every file listed above without missing methods or truncated snippets.
```