"""
SD-FastBackup - Ultra-Fast Deduplicated SD Card Backup Application.
Entry point for QApplication initialization and styling.
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Load Dark Theme stylesheet
    qss_path = os.path.join(os.path.dirname(__file__), "assets", "dark_style.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
