"""
Multi-Threaded Backup Worker for SD-FastBackup.
Orchestrates volume scanning, metadata extraction, deduplication, SQLite cataloging, and FastCopy execution in QThread.
"""
import os
import time
import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal, QObject

from core.metadata import MetadataExtractor
from core.db import DatabaseManager
from core.fastcopy import FastCopyRunner
from utils.path_formatter import filter_source_files, format_full_target_path, normalize_win_path
from utils.drive_detector import get_drive_volume_info


class WorkerSignals(QObject):
    """Signals emitted by BackupWorker across thread boundaries."""
    scan_started = Signal(str)                                # (scan_root_path)
    scan_progress = Signal(int, int, str)                      # (current_count, total_count, current_filename)
    duplicate_found = Signal(str, str, int)                    # (filename, composite_hash, size_bytes)
    transfer_started = Signal(int, int)                        # (total_copy_files, total_copy_bytes)
    transfer_progress = Signal(int, int, str, int)             # (copied_files, total_copy_files, current_filename, file_pct)
    transfer_line = Signal(str)                               # (stdout_output_line)
    read_error = Signal(str, str)                              # (file_path, error_details)
    finished = Signal(dict)                                   # (summary_dict)
    error = Signal(str)                                      # (fatal_error_message)


class BackupWorker(QThread):
    """Background backup orchestrator thread."""

    def __init__(
        self, 
        source_card_path: str, 
        target_dir: str, 
        fastcopy_path: str = "", 
        custom_suffix: str = "", 
        folder_opts: Optional[Dict[str, bool]] = None
    ):
        super().__init__()
        self.source_path = normalize_win_path(os.path.abspath(source_card_path))
        self.target_dir = normalize_win_path(os.path.abspath(target_dir))
        self.fastcopy_path = fastcopy_path
        self.custom_suffix = custom_suffix
        self.folder_opts = folder_opts or {"dcim": True, "private": True, "full_volume": False}
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def run(self):
        try:
            db = DatabaseManager(self.target_dir)
            fastcopy = FastCopyRunner(self.fastcopy_path)

            # 1. Register Volume Info
            vol_info = get_drive_volume_info(self.source_path)
            db.register_volume(vol_info["serial"], vol_info["label"])

            # 2. Discover Source Files
            source_files = filter_source_files(
                self.source_path,
                include_dcim=self.folder_opts.get("dcim", True),
                include_private=self.folder_opts.get("private", True),
                full_volume=self.folder_opts.get("full_volume", False)
            )

            total_files = len(source_files)
            self.signals.scan_started.emit(self.source_path)

            if total_files == 0:
                summary = {'scanned': 0, 'duplicates': 0, 'copied': 0, 'bytes': 0}
                self.signals.finished.emit(summary)
                db.checkpoint()
                return

            files_to_copy = []
            total_copy_bytes = 0
            duplicate_count = 0
            read_error_count = 0

            # 3. Scanning, Metadata Extraction & Deduplication Phase
            for idx, file_path in enumerate(source_files, start=1):
                if self._is_cancelled:
                    db.checkpoint()
                    return

                norm_file_path = normalize_win_path(file_path)
                file_basename = os.path.basename(norm_file_path)
                self.signals.scan_progress.emit(idx, total_files, file_basename)

                # Defensive Metadata & Hash Extraction
                try:
                    composite_hash, size, date_taken, source_type = MetadataExtractor.compute_composite_hash(norm_file_path)
                except Exception as ex:
                    read_error_count += 1
                    err_msg = f"Read error on file '{file_basename}': {ex}"
                    logging.error(err_msg)
                    self.signals.read_error.emit(norm_file_path, str(ex))
                    db.update_transfer_status(f"ERR_{idx}_{time.time()}", norm_file_path, "", "FAILED")
                    continue

                rel_path = normalize_win_path(os.path.relpath(norm_file_path, self.source_path))
                dt_iso = date_taken.isoformat()

                # Register in SQLite catalog
                db.register_file(composite_hash, file_basename, rel_path, size, dt_iso, source_type)

                # Format target path preserving panorama/burst/stack subfolder structure
                target_destination = format_full_target_path(
                    self.target_dir, 
                    date_taken, 
                    file_basename, 
                    suffix=self.custom_suffix,
                    original_rel_path=rel_path
                )

                # Deduplication Check
                if db.is_file_copied(composite_hash):
                    duplicate_count += 1
                    self.signals.duplicate_found.emit(file_basename, composite_hash, size)
                    db.update_transfer_status(composite_hash, norm_file_path, target_destination, 'DUPLICATE_SKIPPED')
                else:
                    files_to_copy.append((norm_file_path, target_destination, composite_hash, size))
                    total_copy_bytes += size

            # 4. Transfer Execution Phase
            copied_count = 0
            if files_to_copy and not self._is_cancelled:
                total_copy_files = len(files_to_copy)
                self.signals.transfer_started.emit(total_copy_files, total_copy_bytes)
                
                source_paths = [item[0] for item in files_to_copy]

                # Run FastCopy / fcp runner and update transfer progress
                # Yields stdout output lines
                for output_line in fastcopy.execute_manifest_copy(source_paths, self.target_dir):
                    if self._is_cancelled:
                        db.checkpoint()
                        return
                    self.signals.transfer_line.emit(output_line)

                # Mark copied status in database and emit progress
                for idx, (src_p, dst_p, h_val, f_size) in enumerate(files_to_copy, start=1):
                    db.update_transfer_status(h_val, src_p, dst_p, 'COPIED')
                    copied_count += 1
                    fname = os.path.basename(src_p)
                    self.signals.transfer_progress.emit(copied_count, total_copy_files, fname, 100)

            summary = {
                'scanned': total_files,
                'duplicates': duplicate_count,
                'copied': copied_count,
                'bytes': total_copy_bytes,
                'errors': read_error_count
            }
            db.checkpoint()
            self.signals.finished.emit(summary)

        except Exception as e:
            logging.exception("Fatal error in BackupWorker pipeline.")
            self.signals.error.emit(str(e))

    def cancel(self):
        """Cancels the ongoing backup operation."""
        self._is_cancelled = True
