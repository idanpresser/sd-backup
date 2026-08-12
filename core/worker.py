"""
Multi-Threaded Backup Worker for SD-FastBackup.
Orchestrates volume scanning, metadata extraction, deduplication, SQLite cataloging, 
Dual-Engine execution (FastCopy CLI for SD Cards / MTPEngine for Mobile Phones), 
and same-volume file renaming with collision avoidance.
"""
import os
import time
import shutil
import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal, QObject

from core.metadata import MetadataExtractor
from core.db import DatabaseManager
from core.fastcopy import FastCopyRunner, parse_fastcopy_stdout_line
from core.mtp_engine import MTPEngine, is_mtp_path, parse_mtp_device_name
from utils.path_formatter import (
    filter_source_files, 
    format_full_target_path, 
    resolve_target_path_collision, 
    normalize_win_path
)
from utils.drive_detector import get_drive_volume_info


class WorkerSignals(QObject):
    """Signals emitted by BackupWorker across thread boundaries."""
    scan_started = Signal(str)                                # (scan_root_path)
    scan_progress = Signal(int, int, str)                      # (current_count, total_count, current_filename)
    duplicate_found = Signal(str, str, float)                  # (filename, composite_hash, size_bytes)
    transfer_started = Signal(int, float)                      # (total_copy_files, total_copy_bytes)
    transfer_progress = Signal(int, int, str, int)             # (copied_files, total_copy_files, current_filename, file_pct)
    transfer_metrics = Signal(dict)                           # (parsed_fastcopy_metrics_dict)
    transfer_line = Signal(str)                               # (stdout_output_line)
    read_error = Signal(str, str)                              # (file_path, error_details)
    finished = Signal(dict)                                   # (summary_dict)
    error = Signal(str)                                      # (fatal_error_message)


class BackupWorker(QThread):
    """Background backup orchestrator thread supporting Dual-Engine Architecture (SD Cards & MTP Phones)."""

    def __init__(
        self, 
        source_card_path: str, 
        target_dir: str, 
        fastcopy_path: str = "", 
        custom_suffix: str = "", 
        folder_opts: Optional[Dict[str, bool]] = None,
        move_mode: bool = False
    ):
        super().__init__()
        self.raw_source_path = source_card_path
        if is_mtp_path(source_card_path):
            self.source_path = source_card_path
            self.is_mtp = True
        else:
            self.source_path = normalize_win_path(os.path.abspath(source_card_path))
            self.is_mtp = False

        self.target_dir = normalize_win_path(os.path.abspath(target_dir))
        self.fastcopy_path = fastcopy_path
        self.custom_suffix = custom_suffix
        self.folder_opts = folder_opts or {"dcim": True, "private": True, "full_volume": False}
        self.move_mode = move_mode
        self.signals = WorkerSignals()
        self._is_cancelled = False

    def run(self):
        try:
            db = DatabaseManager(self.target_dir)

            if self.is_mtp:
                self._run_mtp_pipeline(db)
            else:
                self._run_standard_pipeline(db)

        except Exception as e:
            logging.exception("Fatal error in BackupWorker pipeline.")
            self.signals.error.emit(str(e))

    def _run_mtp_pipeline(self, db: DatabaseManager):
        """Engine B: MTP Mobile Phone Transfer Pipeline (Android & iPhone)."""
        mtp_engine = MTPEngine()
        dev_name = parse_mtp_device_name(self.source_path)

        vol_info = get_drive_volume_info(self.source_path)
        db.register_volume(vol_info["serial"], vol_info["label"])

        self.signals.scan_started.emit(f"MTP Device: {dev_name}")
        self.signals.transfer_line.emit(f"📱 Traversing MTP Phone Virtual Storage: '{dev_name}'...")

        mtp_files = mtp_engine.enumerate_mtp_files(
            dev_name,
            include_dcim=self.folder_opts.get("dcim", True),
            include_private=self.folder_opts.get("private", True),
            full_volume=self.folder_opts.get("full_volume", False)
        )

        total_files = len(mtp_files)
        if total_files == 0:
            self.signals.finished.emit({'scanned': 0, 'duplicates': 0, 'copied': 0, 'bytes': 0})
            db.checkpoint()
            return

        files_to_copy = []
        total_copy_bytes = 0
        duplicate_count = 0
        read_error_count = 0

        for idx, item_info in enumerate(mtp_files, start=1):
            if self._is_cancelled:
                db.checkpoint()
                return

            fname = item_info["name"]
            rel_path = item_info["rel_path"]
            fsize = item_info["size"]
            dt_taken = item_info["date_taken"]
            shell_item = item_info["file_item"]

            self.signals.scan_progress.emit(idx, total_files, fname)

            comp_hash = MetadataExtractor.compute_hash_from_values(dt_taken, fsize)
            dt_iso = dt_taken.isoformat()

            db.register_file(comp_hash, fname, rel_path, fsize, dt_iso, "MTP_PHONE")

            base_target_dest = format_full_target_path(
                self.target_dir,
                dt_taken,
                fname,
                suffix=self.custom_suffix,
                original_rel_path=rel_path
            )
            target_dest = resolve_target_path_collision(base_target_dest)

            if db.is_file_copied(comp_hash):
                duplicate_count += 1
                self.signals.duplicate_found.emit(fname, comp_hash, float(fsize))
                db.update_transfer_status(comp_hash, f"{dev_name}\\{rel_path}", target_dest, 'DUPLICATE_SKIPPED')
            else:
                files_to_copy.append((shell_item, target_dest, comp_hash, fsize, fname))
                total_copy_bytes += fsize

        copied_count = 0
        if files_to_copy and not self._is_cancelled:
            total_copy_files = len(files_to_copy)
            self.signals.transfer_started.emit(total_copy_files, float(total_copy_bytes))

            for idx, (shell_item, dst_p, h_val, f_size, orig_fname) in enumerate(files_to_copy, start=1):
                if self._is_cancelled:
                    db.checkpoint()
                    return

                resolved_dst = resolve_target_path_collision(dst_p)
                success = mtp_engine.copy_mtp_file_to_local(shell_item, resolved_dst)

                if success:
                    copied_count += 1
                    db.update_transfer_status(h_val, f"{dev_name}\\{orig_fname}", resolved_dst, 'COPIED')
                    self.signals.transfer_line.emit(f"📱 MTP Transferred: {os.path.basename(resolved_dst)}")
                    self.signals.transfer_progress.emit(copied_count, total_copy_files, os.path.basename(resolved_dst), 100)
                else:
                    read_error_count += 1
                    self.signals.read_error.emit(orig_fname, "MTP stream transfer failed")

        summary = {
            'scanned': total_files,
            'duplicates': duplicate_count,
            'copied': copied_count,
            'bytes': total_copy_bytes,
            'errors': read_error_count
        }
        db.checkpoint()
        self.signals.finished.emit(summary)

    def _run_standard_pipeline(self, db: DatabaseManager):
        """Engine A: Standard Drive Letter / FastCopy CLI Pipeline."""
        fastcopy = FastCopyRunner(self.fastcopy_path)

        staging_dir = os.path.join(self.target_dir, ".sd_staging")
        if not self.move_mode:
            os.makedirs(staging_dir, exist_ok=True)

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
            self._cleanup_staging(staging_dir)
            self.signals.finished.emit(summary)
            db.checkpoint()
            return

        files_to_copy = []
        total_copy_bytes = 0
        duplicate_count = 0
        read_error_count = 0

        # 3. Scanning & Deduplication Phase
        for idx, file_path in enumerate(source_files, start=1):
            if self._is_cancelled:
                self._cleanup_staging(staging_dir)
                db.checkpoint()
                return

            norm_file_path = normalize_win_path(file_path)
            file_basename = os.path.basename(norm_file_path)
            self.signals.scan_progress.emit(idx, total_files, file_basename)

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

            db.register_file(composite_hash, file_basename, rel_path, size, dt_iso, source_type)

            base_target_dest = format_full_target_path(
                self.target_dir, 
                date_taken, 
                file_basename, 
                suffix=self.custom_suffix,
                original_rel_path=rel_path
            )
            target_destination = resolve_target_path_collision(base_target_dest)

            if db.is_file_copied(composite_hash):
                duplicate_count += 1
                self.signals.duplicate_found.emit(file_basename, composite_hash, float(size))
                db.update_transfer_status(composite_hash, norm_file_path, target_destination, 'DUPLICATE_SKIPPED')
            else:
                files_to_copy.append((norm_file_path, target_destination, composite_hash, size, rel_path))
                total_copy_bytes += size

        # 4. Transfer / Move Execution Phase
        copied_count = 0
        if files_to_copy and not self._is_cancelled:
            total_copy_files = len(files_to_copy)
            self.signals.transfer_started.emit(total_copy_files, float(total_copy_bytes))
            
            if self.move_mode:
                self.signals.transfer_line.emit("🚚 Instant Same-Drive Move Mode active...")
                for idx, (src_p, final_dst_p, h_val, f_size, rel_p) in enumerate(files_to_copy, start=1):
                    if self._is_cancelled:
                        db.checkpoint()
                        return

                    resolved_dst_p = resolve_target_path_collision(final_dst_p)
                    os.makedirs(os.path.dirname(resolved_dst_p), exist_ok=True)

                    if os.path.exists(src_p):
                        shutil.move(src_p, resolved_dst_p)

                    db.update_transfer_status(h_val, src_p, resolved_dst_p, 'COPIED')
                    copied_count += 1
                    fname = os.path.basename(resolved_dst_p)
                    self.signals.transfer_line.emit(f"⚡ Moved: {fname}")
                    self.signals.transfer_progress.emit(copied_count, total_copy_files, fname, 100)

            else:
                source_paths = [item[0] for item in files_to_copy]

                for output_line in fastcopy.execute_manifest_copy(source_paths, staging_dir):
                    if self._is_cancelled:
                        self._cleanup_staging(staging_dir)
                        db.checkpoint()
                        return
                    
                    self.signals.transfer_line.emit(output_line)

                    metrics = parse_fastcopy_stdout_line(output_line)
                    if metrics:
                        self.signals.transfer_metrics.emit(metrics)

                for idx, (src_p, final_dst_p, h_val, f_size, rel_p) in enumerate(files_to_copy, start=1):
                    if self._is_cancelled:
                        self._cleanup_staging(staging_dir)
                        db.checkpoint()
                        return

                    orig_name = os.path.basename(src_p)
                    staged_file_path = os.path.join(staging_dir, orig_name)

                    resolved_dst_p = resolve_target_path_collision(final_dst_p)
                    os.makedirs(os.path.dirname(resolved_dst_p), exist_ok=True)

                    if os.path.exists(staged_file_path):
                        shutil.move(staged_file_path, resolved_dst_p)
                    elif os.path.exists(src_p):
                        shutil.copy2(src_p, resolved_dst_p)

                    db.update_transfer_status(h_val, src_p, resolved_dst_p, 'COPIED')
                    copied_count += 1
                    self.signals.transfer_progress.emit(copied_count, total_copy_files, os.path.basename(resolved_dst_p), 100)

        self._cleanup_staging(staging_dir)

        summary = {
            'scanned': total_files,
            'duplicates': duplicate_count,
            'copied': copied_count,
            'bytes': total_copy_bytes,
            'errors': read_error_count
        }
        db.checkpoint()
        self.signals.finished.emit(summary)

    def _cleanup_staging(self, staging_dir: str):
        """Removes temporary staging directory after batch transfer."""
        if os.path.exists(staging_dir):
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass

    def cancel(self):
        """Cancels the ongoing backup operation."""
        self._is_cancelled = True
