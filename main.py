"""
SD-FastBackup - Ultra-Fast Deduplicated SD Card Backup Application.
Entry point for QApplication initialization and styling.
"""
import sys
import os
import argparse

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="SD-FastBackup")
    parser.add_argument(
        "--rescan-target-after-import", "--sync-on-finish",
        dest="rescan_after_import", action="store_true",
        help="After each backup, reconcile & rescan the destination date folders just written.",
    )
    parser.add_argument(
        "--rescan-full-drive",
        dest="rescan_full_drive", action="store_true",
        help="Make the post-import rescan walk the entire destination drive instead of only "
             "the touched date folders (slower on large archives).",
    )
    parser.add_argument(
        "--index-folder",
        dest="index_folder", type=str, default=None,
        help="Index an existing media folder in-place into .sd_backup_catalog.db and exit.",
    )
    parser.add_argument(
        "--force-reextract",
        dest="force_reextract", action="store_true",
        help="When indexing a folder, force re-extraction of EXIF/MediaInfo for all files.",
    )
    parser.add_argument(
        "--no-recurse",
        dest="no_recurse", action="store_true",
        help="When indexing a folder, do not recurse into subdirectories.",
    )
    # Ignore Qt's own args so both can coexist.
    args, _unknown = parser.parse_known_args(argv)
    return args


def main():
    args = parse_args()

    # Headless CLI Folder Indexing Mode
    if args.index_folder:
        folder_p = os.path.abspath(args.index_folder)
        if not os.path.exists(folder_p) or not os.path.isdir(folder_p):
            print(f"Error: Target folder '{folder_p}' does not exist or is not a directory.")
            sys.exit(1)

        print(f"⚡ Indexing media folder: {folder_p}")
        from core.indexer import FolderIndexer

        def _cli_progress(data):
            status = data.get("status")
            if status == "INDEXING":
                cur = data.get("current", 0)
                tot = data.get("total", 0)
                fname = data.get("current_file", "")
                added = data.get("added", 0)
                skipped = data.get("skipped", 0)
                print(f"\r[{cur}/{tot}] Indexing: {fname} (Added: {added}, Skipped: {skipped})", end="", flush=True)

        try:
            stats = FolderIndexer.index_folder(
                root_dir=folder_p,
                progress_callback=_cli_progress,
                force_reextract=args.force_reextract,
                include_subdirs=not args.no_recurse
            )
            print(f"\n✅ Indexing complete!")
            print(f"  • Discovered: {stats['total_discovered']}")
            print(f"  • Added: {stats['added_records']}")
            print(f"  • Skipped: {stats['skipped_records']}")
            print(f"  • Metadata Extracted: {stats['metadata_extracted']}")
            print(f"  • Errors: {stats['errors']}")
            sys.exit(0 if stats["errors"] == 0 else 1)
        except Exception as e:
            print(f"\n❌ Indexing failed: {e}")
            sys.exit(1)

    app = QApplication(sys.argv)

    # Load Dark Theme stylesheet via resource path helper
    from utils.resource_path import get_asset_path
    qss_path = get_asset_path("dark_style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    # CLI flags override persisted config for this session.
    if args.rescan_after_import or args.rescan_full_drive:
        window.drive_selector.rescan_cb.setChecked(True)
    if args.rescan_full_drive:
        window._rescan_full_drive = True
    window.show_default()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
