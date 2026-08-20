"""
SD-FastBackup - Ultra-Fast Deduplicated SD Card Backup Application.
Entry point for QApplication initialization and styling.
"""
import sys
import os
import argparse
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
    # Ignore Qt's own args so both can coexist.
    args, _unknown = parser.parse_known_args(argv)
    return args


def main():
    args = parse_args()
    app = QApplication(sys.argv)

    # Load Dark Theme stylesheet
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "dark_style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    # CLI flags override persisted config for this session.
    if args.rescan_after_import or args.rescan_full_drive:
        window.drive_selector.rescan_cb.setChecked(True)
    if args.rescan_full_drive:
        window._rescan_full_drive = True
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
