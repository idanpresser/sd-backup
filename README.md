# SD-FastBackup

**Ultra-fast, deduplicated offload for photographers and videographers.** Dump card after card into one organized archive — no duplicates, resumable transfers, and a full metadata catalog — then cull the results over your LAN with its companion app, **QuickImageCullLAN**.

<p>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="Platform" src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey">
  <img alt="UI" src="https://img.shields.io/badge/UI-PySide6%20(Qt%206)-41cd52">
  <img alt="Tests" src="https://img.shields.io/badge/tests-183%20passing-brightgreen">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

---

## Why this exists

Offloading a shoot from five or ten SD cards is slow, error-prone, and a great way to create duplicate copies of the same frames. Full cryptographic hashing of multi-terabyte 4K/8K footage takes *longer than the copy itself*. And re-inserting a card you already backed up shouldn't waste an hour re-copying files you already have.

SD-FastBackup solves this with a **lightweight composite hash** (`date taken` + `file size`) that identifies identical files instantly — no full-content hashing — backed by a persistent SQLite catalog so every transfer is deduplicated and resumable.

```
   SD cards / phones                SD-FastBackup                 Your archive drive          QuickImageCullLAN
  ┌──────────────────┐          ┌────────────────────┐        ┌──────────────────────┐      ┌───────────────────┐
  │  📷 EOS_DIGITAL  │          │  scan → hash →     │        │  2026/2026-08/…      │      │  Rate & cull over │
  │  📱 Pixel (MTP)  │  ───────▶│  dedup → copy →    │ ─────▶ │  _DSC5891.ARW        │ ───▶ │  the LAN, then    │
  │  💾 Rugged SSD   │          │  catalog           │        │  .sd_backup_catalog  │      │  export XMP       │
  └──────────────────┘          └────────────────────┘        └──────────────────────┘      └───────────────────┘
                                                                  (SQLite catalog)             (reads catalog read-only)
```

**SD-FastBackup is the ingest engine. [QuickImageCullLAN](#the-companion-quickimageculllan) is the culling front-end.** They are independent projects that meet at one contract: the SQLite catalog file. You can use SD-FastBackup entirely on its own.

---

## Features

- ⚡ **Fast dedup without full hashing** — a composite `SHA256(date_taken + size_bytes)` identifies duplicates across cards and re-inserts instantly.
- 🔁 **Resumable & idempotent** — interrupted transfers pick up where they left off; a re-inserted card copies nothing new.
- 🧠 **Dual-engine ingest** — SD cards / drives via an optional [FastCopy](https://fastcopy.jp/) accelerator, phones via **MTP/PTP** (Windows shell).
- 🗂️ **Organized output** — files land in a `YYYY/YYYY-MM/YYYY-MM-DD/` tree with clean, collision-safe names (e.g. `20260811_150626_YourSuffix_0113.MP4`).
- 📇 **Rich metadata catalog** — EXIF / MediaInfo / (optional) ExifTool extraction into a queryable SQLite catalog: camera, lens, ISO, dimensions, codec, GPS, and more.
- 🔍 **Post-import reconcile** — optionally rescan the destination after a backup to index files added outside the app and backfill missing metadata (scoped to touched date-folders, so a multi-TB archive is never re-walked).
- 🛟 **Source is never touched** — no source file is ever modified or deleted. (An opt-in *move* mode exists for same-drive reorganization.)
- 🎛️ **Configurable media filter** — a full, editable allowlist of photo/video/audio extensions incl. RAW and Insta360 (`.insp`/`.insv`).

---

## How it works

1. **Scan.** The selected source (SD card, folder, or MTP phone) is walked; junk and system files are filtered out by a multi-layer media allowlist.
2. **Hash.** For each media file, `date_taken` is extracted (EXIF → MediaInfo container → filesystem `mtime` fallback) and combined with the exact byte size into a composite hash: `SHA256(f"{date_taken_iso}_{file_size_bytes}")`. This is a **stable identifier that survives renames and re-scans**.
3. **Dedup.** Each hash is checked against the catalog. Already-copied files are skipped and reported; only new/unfinished files are queued.
4. **Copy.** Queued files are transferred (FastCopy if configured, otherwise a safe staged copy), renamed by capture time, and organized into the date-folder tree.
5. **Catalog.** Every file's hash, paths, size, capture date, and extended metadata are written to `.sd_backup_catalog.db` at the root of the target drive.
6. **Finalize.** At the end of a session the catalog's write-ahead log is flushed to disk and a monotonic `generation` marker is bumped, leaving the catalog in a clean, consistent state for downstream readers.

---

## Requirements

- **OS:** Windows 10 / 11 (uses `pywin32`, Windows MTP shell, and — optionally — FastCopy).
- **Python:** 3.10 or newer.
- **Optional — [FastCopy](https://fastcopy.jp/):** the standalone `FastCopy.exe` for maximum transfer throughput. Without it, SD-FastBackup falls back to a built-in staged copy.
- **Optional — [ExifTool](https://exiftool.org/):** if `exiftool.exe` is on your `PATH` or in `bin/`, it is used for the richest metadata extraction. Not required.

---

## Installation

```bash
# 1. Clone
git clone <your-fork-url> sd_backup
cd sd_backup

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

**Optional accelerators**
- Download **FastCopy** and note the path to `FastCopy.exe` (you'll point the app at it in settings).
- Drop **`exiftool.exe`** into `bin/` (it is git-ignored) for the best metadata coverage.

---

## Quick start

```bash
python main.py      # or double-click start.bat
```

Then, in the UI:

1. **Source** — pick your SD card, a folder, or a connected phone (MTP/PTP).
2. **Backup Target Destination** — choose the archive drive/folder. The catalog lives here.
3. **Options** — choose which folders to scan (`DCIM/`, `PRIVATE/`, or Full Storage) and, optionally, a custom filename suffix (e.g. your name for copyright).
4. Press **Start Backup**. Watch progress, live transfer speed, and a running duplicate log. Swap cards and repeat — the catalog remembers everything.

---

## Configuration

Settings are persisted to **`config.json`** in the project root (the GUI reads and writes this for you; you can also edit it by hand).

| Key | Type | Description |
|---|---|---|
| `source_path` | string | Last-used source (card/folder path, or an `MTP:\…` device path). |
| `target_directory` | string | Archive destination. The catalog `.sd_backup_catalog.db` is created at its root. |
| `custom_suffix` | string | Optional token inserted into destination filenames (e.g. `"IdanPresser(C)"`). |
| `fastcopy_path` | string | Absolute path to `FastCopy.exe`. Empty = use the built-in staged copy. |
| `media_extensions` | string[] | Editable allowlist of extensions to ingest (images, RAW, video, audio, sidecars). |
| `subfolder_options.dcim` | bool | Scan the `DCIM/` tree. |
| `subfolder_options.private` | bool | Scan camcorder structures (`PRIVATE/`, `MP_ROOT`, …). |
| `subfolder_options.full_volume` | bool | Scan the entire source volume, not just known media folders. |
| `subfolder_options.move_mode` | bool | Same-drive **move** instead of copy (0-byte instant reorganize). Only offered when source and target share a drive. |
| `auto_rescan_after_import` | bool | After each backup, reconcile the destination: index files added outside the app and backfill metadata. Scoped to the date-folders just written. |
| `rescan_full_drive` | bool | Make the post-import rescan walk the **entire** destination instead of only touched folders (slower on large archives). |

<details>
<summary>Example <code>config.json</code></summary>

```json
{
  "source_path": "E:\\DCIM",
  "target_directory": "I:\\Archive_2026",
  "custom_suffix": "YourName(C)",
  "fastcopy_path": "C:\\Tools\\FastCopy\\FastCopy.exe",
  "media_extensions": [".arw", ".cr3", ".jpg", ".mp4", ".mov", ".insv", ".insp"],
  "subfolder_options": {
    "dcim": true,
    "private": true,
    "full_volume": false,
    "move_mode": false
  },
  "auto_rescan_after_import": true,
  "rescan_full_drive": false
}
```
</details>

### Command-line flags

The GUI accepts a few flags that override persisted config for the session:

```bash
python main.py --rescan-target-after-import   # (alias: --sync-on-finish)
python main.py --rescan-full-drive            # rescan the whole destination, not just touched folders
```

---

## The companion: QuickImageCullLAN

Once your shoot is offloaded, **QuickImageCullLAN** turns the archive into a fast, LAN-hosted culling station:

- A FastAPI + React app that **reads the SD-FastBackup catalog read-only** and serves lightweight WebP proxies and video posters/transcodes to any phone, tablet, or laptop on your network.
- The whole household rates in parallel; ratings export back to the archive as **XMP sidecars** that Lightroom, darktable, and digiKam understand.

**The contract between the two projects** (see [`ARCHITECTURE.md`](ARCHITECTURE.md) §3.1):

- The catalog is joined on the stable `composite_hash` — never on local row ids.
- QuickImageCullLAN attaches the catalog **read-only and `immutable=1`**; SD-FastBackup therefore guarantees the catalog is **quiescent at session end** (WAL flushed, sidecars dropped) so the reader sees every committed row and never a torn page.
- SD-FastBackup publishes a monotonic `catalog_meta.generation` marker so the reader can cheaply detect changes and re-scan.
- `target_relative_path` is always archive-relative (no drive letters, UNC, or `..`), so the reader can safely resolve `archive_root / target_relative_path`.

The two repos evolve independently as long as that schema contract holds.

---

## Project structure

```
sd_backup/
├── main.py                 # GUI entry point (+ CLI flags)
├── config.json             # persisted settings
├── app/
│   ├── main_window.py      # PySide6 main window
│   └── components/         # drive selector, progress panel, log console, DB viewer…
├── core/
│   ├── worker.py           # BackupWorker (QThread) — scan → hash → dedup → copy → catalog
│   ├── metadata.py         # composite hashing + EXIF/MediaInfo/ExifTool extraction
│   ├── db.py               # SQLite catalog: schema, dedup, generation marker, finalize()
│   ├── fastcopy.py         # FastCopy CLI wrapper + progress parsing
│   ├── mtp_engine.py       # MTP/PTP phone ingest (Windows shell)
│   └── sync_engine.py      # disk↔catalog reconciliation (scoped or full)
├── utils/                  # media filter, path formatting, drive detection, renaming
├── tests/                  # pytest suite (183 tests)
├── ARCHITECTURE.md         # technical design + the consumer contract (§3.1)
└── prd.md                  # product requirements
```

---

## Development

```bash
# Run the full test suite
python -m pytest -q

# Run a single module
python -m pytest tests/test_worker.py -q
```

- **Design docs:** [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`prd.md`](prd.md) describe the system and its rationale in depth.
- **Metadata note:** the media allowlist (`utils/media_filter.py`) and the date-extraction extension lists (`core/metadata.py`) are kept in sync so any cataloged format is eligible for real capture-date extraction — otherwise it would silently fall back to `mtime`, which corrupts the culler's timeline.

---

## Contributing

Contributions are welcome!

1. **Fork** the repo and create a topic branch: `git checkout -b my-feature`.
2. **Write a test first.** This project is test-driven; new behavior should come with coverage in `tests/`.
3. **Keep the suite green:** `python -m pytest -q`.
4. **Match the surrounding style** — small, focused modules; clear docstrings; no source-file mutation on the ingest path.
5. **Open a pull request** describing the change and its motivation. Reference any related design doc section.

Good first areas: additional camera folder structures, metadata extractors for new formats, cross-platform (macOS/Linux) transfer backends, and UI polish.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| *"FastCopy executable not found"* | Leave `fastcopy_path` empty to use the built-in copier, or point it at a valid `FastCopy.exe`. |
| **Phone shows 0 files** | Unlock the phone, switch its USB mode to *Photos (PTP)*, and enable *Full Storage* in the app. |
| **Dates look wrong / clustered by copy time** | The file lacked EXIF/container metadata and fell back to `mtime`. Install ExifTool (`bin/exiftool.exe`) for better coverage. |
| **Duplicates keep re-copying** | Ensure you're pointing at the *same* target directory each session — the catalog lives there. |

---

## License

Released under the **MIT License**. See [`LICENSE`](LICENSE).

## Acknowledgements

- [FastCopy](https://fastcopy.jp/) — the fastest file copy engine on Windows.
- [ExifTool](https://exiftool.org/) by Phil Harvey — metadata extraction.
- [PySide6 / Qt](https://www.qt.io/qt-for-python) — the GUI framework.
