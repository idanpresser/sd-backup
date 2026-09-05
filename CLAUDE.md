# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:1105d646 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->

## Commands

```bash
# Environment (Windows-only app: pywin32, Windows MTP shell, FastCopy)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Tests (194 tests, ~45s; no pytest config file, no conftest.py)
python -m pytest -q
python -m pytest tests/test_worker.py -q            # one module
python -m pytest tests/test_db.py::test_file_catalog_and_deduplication -q  # one test

# Run the GUI
python main.py           # or start.bat

# CLI modes / session overrides (see main.py:parse_args)
python main.py --index-folder "D:\Archive"          # headless: index in place, then exit
python main.py --index-folder "D:\Archive" --force-reextract --no-recurse
python main.py --rescan-target-after-import         # alias: --sync-on-finish
python main.py --rescan-full-drive

# Standalone PyInstaller onedir build -> dist/SD-FastBackup/
build.bat            # wraps: python scripts\build_executable.py (uses sd_backup.spec)

# Maintenance helpers (operate directly on an archive + its catalog)
python clean_blacklist.py     # purge blacklisted non-media files from target + catalog rows
python rename_suffix.py       # rename filename suffixes on disk and in transfer_manifest
```

`tests/steel_thread_mtp.py` is **not** collected by pytest (name doesn't match `test_*`). It is a manual hardware harness that validates the 7 MTP layers against a physically connected phone.

## Architecture

Read `ARCHITECTURE.md` (esp. §3 schema and §3.1 consumer contract) and `README.md` before changing the ingest path or the catalog schema.

**Pipeline:** `scan → extract date_taken → composite hash → dedup against catalog → copy/move → rename+organize → catalog → finalize`. Everything after the button click runs on `BackupWorker` (a `QThread`); the GUI only reacts to `WorkerSignals`.

**Layers**
- `main.py` — QApplication bootstrap, argparse, and the headless `--index-folder` path (which imports `core.indexer` and never creates a QApplication).
- `app/main_window.py` + `app/components/` — PySide6 widgets. `MainWindow(config_path=...)` owns loading/saving `config.json` and constructs the worker.
- `core/worker.py` — orchestrator with **two ingest engines** selected by `is_mtp_path(source)`: `_run_standard_pipeline` (drive letters/folders → FastCopy) and `_run_mtp_pipeline` (phones → Windows Shell COM).
- `core/metadata.py` — `MetadataExtractor`: date extraction (EXIF → MediaInfo container → `mtime`), composite hashing, and full metadata (ExifTool if resolvable, else exifread/pymediainfo).
- `core/db.py` — `DatabaseManager`: the only writer of `.sd_backup_catalog.db`, which lives at the **root of the target directory**, not in the repo.
- `core/fastcopy.py`, `core/mtp_engine.py`, `core/sync_engine.py`, `core/indexer.py` — transfer backends and disk↔catalog reconciliation.
- `utils/` — media allowlist, path/filename formatting, drive detection, frozen-build path resolution, archive maintenance.

**Identity — the composite hash.** `SHA256(f"{date_taken.strftime('%Y-%m-%dT%H:%M:%S')}_{size_bytes}")`. It is the primary key of the whole system: dedup, every join, and the external consumer contract. Never change its formula or formatting — it would orphan every existing archive and break QuickImageCullLAN. MTP files use `compute_hash_from_values()` with properties read off the device (no local file to stat).

**Transfer staging.** The standard pipeline copies into a hidden `.sd_staging/` at the target root, then `shutil.move`s each file into its final `YYYY/YYYY-MM/YYYY-MM-DD/` path — a same-volume rename, so it is instant. `move_mode` skips staging entirely and moves sources directly (the only mode that mutates the source). `_cleanup_staging` must run on every exit path, including cancel.

## Invariants

These are enforced by tests and by downstream consumers — violating one is a silent data bug, not a crash.

- **Never mutate or delete source files** outside `move_mode`. The ingest path is read-only on the card.
- **`target_relative_path` must stay archive-relative.** `register_file()` is the single guarded write path: it normalizes, and stores `NULL` rather than persisting a drive-lettered/UNC/`..`-escaping value. Don't add a second write path that bypasses that check.
- **The catalog must be quiescent at session end.** `finalize()` TRUNCATE-checkpoints the WAL and converts to `journal_mode=DELETE` so the `-wal`/`-shm` sidecars are dropped; `generation` is bumped only after that. The consumer attaches `mode=ro&immutable=1`, which ignores the WAL — anything left in it is invisible to them.
- **`utils/media_filter.py` and `MetadataExtractor.{IMAGE,VIDEO,AUDIO}_EXTENSIONS` must stay in sync.** A format that is cataloged but not date-extractable silently falls back to `mtime`, which corrupts the culler's timeline. `metadata.py` unions the media_filter defaults with `_LEGACY_*` sets for exactly this reason.
- **Duplicates cause zero DB writes** — a re-inserted card is a pure read.
- **Byte counts in Qt signals are `float`.** `Signal(int)` is a 32-bit C++ int and overflows past ~2.14 GB.
- **COM needs `_ensure_coinitialize()`** before any Shell/MTP call on a worker thread.
- **Resolve paths through `utils/resource_path.py`** (`get_asset_path`, `get_bin_path`, `get_config_path`) — never `__file__`-relative or bare relative paths, or the PyInstaller onedir build breaks. New modules and components also need adding to `hiddenimports` in `sd_backup.spec`.

## Conventions

- **Tests come first** — the suite is the spec for this codebase, and most invariants above have a dedicated `tests/test_*.py` named after them (`test_target_relative_path_guard`, `test_db_finalize_quiescent`, `test_large_file_overflow`, `test_metadata_extension_coverage`).
- **Qt tests set `os.environ["QT_QPA_PLATFORM"] = "offscreen"` before importing PySide6** and create a module-scoped `QApplication` fixture. There is no `conftest.py`, so each GUI test file does this itself.
- `utils/media_filter.py` keeps the active extension set in **module-level mutable state** (`_ACTIVE_MEDIA_EXTENSIONS`). Tests that mutate it must restore it, or they leak into later tests.
- Windows paths flow through `normalize_win_path()`; MTP sources are `MTP:\…` strings and are never `os.path.abspath`'d.
- `CLAUDE.md` and `AGENTS.md` are independent files sharing a bd-managed block (`<!-- BEGIN BEADS INTEGRATION -->`). Mirror substantive edits across both; don't hand-edit inside the managed markers.
