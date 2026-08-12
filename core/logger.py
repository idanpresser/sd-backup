"""
Custom Qt Signal Logging Handler for SD-FastBackup.
Routes standard Python logging messages safely to PySide6 GUI console widgets across threads.
"""
import logging
from PySide6.QtCore import QObject, Signal


class LogSignalEmitter(QObject):
    log_emitted = Signal(str, str)  # (formatted_message, level_name)


class QtSignalingLogHandler(logging.Handler):
    """
    Python logging handler that emits a Qt Signal whenever a log record is processed.
    Thread-safe signal emission to Qt main GUI thread.
    """

    def __init__(self):
        super().__init__()
        self.emitter = LogSignalEmitter()
        self.log_emitted = self.emitter.log_emitted

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            level = record.levelname
            self.emitter.log_emitted.emit(msg, level)
        except Exception:
            self.handleError(record)
