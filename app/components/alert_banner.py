"""
Non-blocking Alert Banner Component for SD-FastBackup.
Displays non-blocking toast/banner alerts for card read errors and system warnings.
"""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt


class AlertBannerWidget(QFrame):
    """Non-blocking notification alert banner with dismiss action."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self.hide()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)

        self.icon_label = QLabel("⚠️")
        self.icon_label.setStyleSheet("font-size: 16px;")

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-weight: bold; color: #FFFFFF;")

        self.dismiss_btn = QPushButton("✕")
        self.dismiss_btn.setFixedSize(24, 24)
        self.dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #FFFFFF;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 12px;
            }
        """)
        self.dismiss_btn.clicked.connect(self.dismiss)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.message_label, 1)
        layout.addWidget(self.dismiss_btn)

    def show_alert(self, message: str, level: str = "WARNING"):
        """Displays non-blocking alert with color styling based on level."""
        self.message_label.setText(message)

        if level.upper() == "ERROR":
            self.icon_label.setText("🛑")
            self.setStyleSheet("""
                AlertBannerWidget {
                    background-color: #8B0000;
                    border: 1px solid #FF4D4D;
                    border-radius: 4px;
                }
            """)
        else:
            self.icon_label.setText("⚠️")
            self.setStyleSheet("""
                AlertBannerWidget {
                    background-color: #7A5200;
                    border: 1px solid #FFC107;
                    border-radius: 4px;
                }
            """)

        self.show()

    def dismiss(self):
        """Hides the alert banner."""
        self.hide()
