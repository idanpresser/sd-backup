"""
Multi-Threaded Backup Worker for SD-FastBackup.
Orchestrates volume scanning, metadata extraction, deduplication, SQLite cataloging, 
Dual-Engine execution (FastCopy CLI for SD Cards / MTPEngine for Mobile Phones), 
and same-volume file renaming with collision avoidance.
"""
import os
import sys
import time
import shutil
import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import QThread, Signal, QObject

from core.metadata import MetadataExtractor
from core.db import DatabaseManager, register_metadata_batched
from core.fastcopy import FastCopyRunner, parse_fastcopy_stdout_line
from core.mtp_engine import MTPEngine, is_mtp_path, parse_mtp_device_name, parse_mtp_subfolder_path, _ensure_coinitialize
from core.sync_engine import execute_sync
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
    transfer_progress = Signal(int, int, str)                  # (copied_files, total_copy_files, current_filename)
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
        move_mode: bool = False,
        auto_rescan: bool = False,
        rescan_full_drive: bool = False
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
        self.auto_rescan = auto_rescan
        self.rescan_full_drive = rescan_full_drive
        self.signals = WorkerSignals()
        self._is_cancelled = False
        # Root-relative destination date-folders written this session; used to scope the
        # optional post-import reconcile so it never re-walks the whole archive.
        self._touched_dirs = set()

    def run(self):
        _ensure_coinitialize()
        db = None
        try:
            db = DatabaseManager(self.target_dir)

            if self.is_mtp:
                self._run_mtp_pipeline(db)
            else:
                self._run_standard_pipeline(db)

            if self.auto_rescan and not self._is_cancelled:
                self._run_post_import_reconcile()

        except Exception as e:
            logging.exception("Fatal error in BackupWorker pipeline.")
            self.signals.error.emit(str(e))
        finally:
            # Bump the generation marker (consumer change signal) then leave the catalog
            # quiescent — WAL flushed, sidecars dropped — so the culler's immutable=1 attach
            # sees every committed row plus the new generation, and never reads a torn page.
            if db is not None:
                try:
                    db.bump_generation()
                except Exception:
                    logging.warning("Could not bump catalog generation.", exc_info=True)
                try:
                    db.finalize()
                except Exception:
                    logging.warning("Could not finalize catalog after session.", exc_info=True)

    def _run_mtp_pipeline(self, db: DatabaseManager):
        """Engine B: MTP Mobile Phone Transfer Pipeline (Android & iPhone)."""
        _ensure_coinitialize()
        mtp_engine = MTPEngine()
        dev_name = parse_mtp_device_name(self.source_path)
        subfolder_path = parse_mtp_subfolder_path(self.source_path)

        vol_info = get_drive_volume_info(self.source_path)
        db.register_volume(vol_info["serial"], vol_info["label"])

        display_name = f"{dev_name}\\{subfolder_path}" if subfolder_path else dev_name
        self.signals.scan_started.emit(f"MTP Device: {display_name}")
        self.signals.transfer_line.emit(f"📱 Traversing MTP Phone Storage: '{display_name}'...")

        mtp_files = mtp_engine.enumerate_mtp_files(
            dev_name,
            subfolder_path=subfolder_path,
            include_dcim=self.folder_opts.get("dcim", True),
            include_private=self.folder_opts.get("private", True),
            full_volume=self.folder_opts.get("full_volume", False)
        )

        total_files = len(mtp_files)
        if total_files == 0:
            guidance = (
                f"0 media files returned by Windows for '{display_name}'. "
                "Try unlocking your phone, switching USB mode on your phone to 'Photos (PTP)', "
                "and checking 'Full Storage' in SD-FastBackup."
            )
            self.signals.read_error.emit(display_name, guidance)
            self.signals.transfer_line.emit(f"⚠️ MTP / PTP Notice: {guidance}")
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

            if db.is_file_copied(comp_hash):
                duplicate_count += 1
                self.signals.duplicate_found.emit(fname, comp_hash, float(fsize))
                # Ignore duplicates: zero DB writes
                continue

            base_target_dest = format_full_target_path(
                self.target_dir,
                dt_taken,
                fname,
                suffix=self.custom_suffix,
                original_rel_path=rel_path
            )
            target_dest = resolve_target_path_collision(base_target_dest)
            files_to_copy.append((shell_item, target_dest, comp_hash, fsize, fname, rel_path, dt_iso))
            total_copy_bytes += fsize

        copied_count = 0
        metadata_targets = []
        if files_to_copy and not self._is_cancelled:
            total_copy_files = len(files_to_copy)
            self.signals.transfer_started.emit(total_copy_files, float(total_copy_bytes))

            with db.batch() as conn:
                for idx, (shell_item, dst_p, h_val, f_size, orig_fname, orig_rel_p, dt_iso) in enumerate(files_to_copy, start=1):
                    if self._is_cancelled:
                        break

                    resolved_dst = resolve_target_path_collision(dst_p)
                    success = mtp_engine.copy_mtp_file_to_local(shell_item, resolved_dst)

                    if success:
                        copied_count += 1
                        dest_filename = os.path.basename(resolved_dst)
                        target_rel_p = normalize_win_path(os.path.relpath(resolved_dst, self.target_dir))

                        touched = os.path.dirname(target_rel_p)
                        if touched:
                            self._touched_dirs.add(touched)

                        db.register_file(
                            h_val,
                            orig_fname,
                            orig_rel_p,
                            f_size,
                            dt_iso,
                            "MTP_PHONE",
                            destination_filename=dest_filename,
                            target_relative_path=target_rel_p,
                            conn=conn,
                        )
                        db.update_transfer_status(
                            h_val, f"{dev_name}\\{orig_fname}", resolved_dst, 'COPIED', conn=conn
                        )
                        metadata_targets.append((resolved_dst, h_val, orig_fname))
                        self.signals.transfer_line.emit(f"📱 MTP Transferred: {dest_filename}")
                        self.signals.transfer_progress.emit(copied_count, total_copy_files, dest_filename)
                    else:
                        read_error_count += 1
                        self.signals.read_error.emit(orig_fname, "MTP stream transfer failed")

            if self._is_cancelled:
                db.checkpoint()
                return

        # The phone's device name stands in as camera_make when the file carries none.
        self._extract_metadata_batched(db, metadata_targets, camera_make_fallback=dev_name)

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

        vol_info = get_drive_volume_info(self.source_path)
        db.register_volume(vol_info["serial"], vol_info["label"])

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

            if db.is_file_copied(composite_hash):
                duplicate_count += 1
                self.signals.duplicate_found.emit(file_basename, composite_hash, float(size))
                # Ignore duplicates: zero DB writes
                continue

            base_target_dest = format_full_target_path(
                self.target_dir, 
                date_taken, 
                file_basename, 
                suffix=self.custom_suffix,
                original_rel_path=rel_path
            )
            target_destination = resolve_target_path_collision(base_target_dest)
            files_to_copy.append((norm_file_path, target_destination, composite_hash, size, rel_path, file_basename, dt_iso, source_type))
            total_copy_bytes += size

        copied_count = 0
        metadata_targets = []
        if files_to_copy and not self._is_cancelled:
            total_copy_files = len(files_to_copy)
            self.signals.transfer_started.emit(total_copy_files, float(total_copy_bytes))

            if self.move_mode:
                self.signals.transfer_line.emit("🚚 Instant Same-Drive Move Mode active...")
                with db.batch() as conn:
                    for idx, (src_p, final_dst_p, h_val, f_size, rel_p, orig_basename, dt_iso, src_type) in enumerate(files_to_copy, start=1):
                        if self._is_cancelled:
                            break

                        resolved_dst_p = resolve_target_path_collision(final_dst_p)
                        os.makedirs(os.path.dirname(resolved_dst_p), exist_ok=True)

                        if os.path.exists(src_p):
                            shutil.move(src_p, resolved_dst_p)

                        if self._finalize_transfer(
                            db, resolved_dst_p, h_val, orig_basename, rel_p, f_size, dt_iso, src_type, src_p,
                            conn=conn,
                        ):
                            copied_count += 1
                            metadata_targets.append((resolved_dst_p, h_val, orig_basename))
                            dest_filename = os.path.basename(resolved_dst_p)
                            self.signals.transfer_line.emit(f"⚡ Moved: {dest_filename}")
                            self.signals.transfer_progress.emit(copied_count, total_copy_files, dest_filename)
                        else:
                            read_error_count += 1

                if self._is_cancelled:
                    # Rows for what was already moved are committed; their extended
                    # metadata is recoverable later via backfill_missing_metadata().
                    db.checkpoint()
                    return

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

                with db.batch() as conn:
                    for idx, (src_p, final_dst_p, h_val, f_size, rel_p, orig_basename, dt_iso, src_type) in enumerate(files_to_copy, start=1):
                        if self._is_cancelled:
                            break

                        orig_name = os.path.basename(src_p)
                        staged_file_path = os.path.join(staging_dir, orig_name)

                        resolved_dst_p = resolve_target_path_collision(final_dst_p)
                        os.makedirs(os.path.dirname(resolved_dst_p), exist_ok=True)

                        if os.path.exists(staged_file_path):
                            shutil.move(staged_file_path, resolved_dst_p)
                        elif os.path.exists(src_p):
                            shutil.copy2(src_p, resolved_dst_p)

                        if self._finalize_transfer(
                            db, resolved_dst_p, h_val, orig_basename, rel_p, f_size, dt_iso, src_type, src_p,
                            conn=conn,
                        ):
                            copied_count += 1
                            metadata_targets.append((resolved_dst_p, h_val, orig_basename))
                            dest_filename = os.path.basename(resolved_dst_p)
                            self.signals.transfer_progress.emit(copied_count, total_copy_files, dest_filename)
                        else:
                            read_error_count += 1

                if self._is_cancelled:
                    self._cleanup_staging(staging_dir)
                    db.checkpoint()
                    return

        self._extract_metadata_batched(db, metadata_targets)
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

    def _finalize_transfer(
        self,
        db: DatabaseManager,
        resolved_dst_p: str,
        h_val: str,
        orig_basename: str,
        rel_p: str,
        f_size: int,
        dt_iso: str,
        src_type: str,
        src_p: str,
        conn=None,
    ) -> bool:
        """Record the outcome of a single file transfer.

        Returns True only if the destination file actually exists on disk, in which
        case it is cataloged as COPIED. If the destination is missing — card pulled
        mid-copy, staging failure, or I/O error — nothing is cataloged; the transfer is
        recorded as FAILED and a read_error is surfaced. This prevents a phantom COPIED
        row pointing at a file that was never written.

        Extended metadata is NOT extracted here: it is collected for the caller's
        batched pass (see _extract_metadata_batched), because spawning ExifTool per file
        cost ~530ms against a 0.6ms rename.
        """
        if not os.path.exists(resolved_dst_p):
            # Nothing was written to disk. Do NOT catalog the file: a file_catalog row
            # would be a phantom COPIED entry pointing at a non-existent file (which the
            # downstream culler would try to serve). We also cannot record a bare FAILED
            # transfer_manifest row — its composite_hash FK references file_catalog, which
            # has no row here — so the failure is surfaced via signal + error count only.
            logging.error(
                f"Transfer target missing after copy: '{resolved_dst_p}' (source '{src_p}')"
            )
            self.signals.read_error.emit(
                orig_basename, "Transfer failed: destination file missing after copy"
            )
            return False

        dest_filename = os.path.basename(resolved_dst_p)
        target_rel_path = normalize_win_path(os.path.relpath(resolved_dst_p, self.target_dir))

        touched = os.path.dirname(target_rel_path)
        if touched:
            self._touched_dirs.add(touched)

        db.register_file(
            h_val,
            orig_basename,
            rel_p,
            f_size,
            dt_iso,
            src_type,
            destination_filename=dest_filename,
            target_relative_path=target_rel_path,
            conn=conn,
        )
        db.update_transfer_status(h_val, src_p, resolved_dst_p, 'COPIED', conn=conn)
        return True

    def _extract_metadata_batched(
        self,
        db: DatabaseManager,
        targets: list,
        camera_make_fallback: Optional[str] = None,
        chunk_size: int = 200,
    ):
        """Extract and catalog extended metadata for a whole transfer in batches.

        `targets` is a list of (destination_path, composite_hash, original_filename).
        ExifTool is invoked once per chunk rather than once per file, and each chunk's
        catalog writes share one connection, which is what keeps move mode's organize
        step near the cost of the renames themselves.
        """
        if not targets:
            return

        total = len(targets)
        self.signals.transfer_line.emit(f"🔍 Extracting metadata for {total} file(s)...")

        register_metadata_batched(
            db,
            targets,
            chunk_size=chunk_size,
            progress_callback=lambda done, tot: self.signals.transfer_line.emit(
                f"🔍 Metadata: {done}/{tot}"
            ),
            camera_make_fallback=camera_make_fallback,
        )

    def _run_post_import_reconcile(self):
        """Reconcile the destination against the catalog after an import.

        Indexes files that appeared on disk without a catalog record (e.g. manually
        dropped from another card) and backfills metadata. Scoped by default to the
        date-folders this session touched so a multi-TB archive is not re-walked every
        import; a full-drive pass is opt-in via rescan_full_drive. Missing records are
        NOT purged here — a file could be mid-write right after a backup.
        """
        scope = None if self.rescan_full_drive else sorted(self._touched_dirs)
        if not self.rescan_full_drive and not scope:
            return  # nothing was written; nothing to reconcile

        label = "full destination" if self.rescan_full_drive else f"{len(scope)} touched folder(s)"
        self.signals.transfer_line.emit(f"🔄 Reconciling {label} (rescan after import)...")
        try:
            summary = execute_sync(
                self.target_dir,
                remove_missing=False,
                add_uncataloged=True,
                uncataloged_action="ADD_TO_DB",
                scope_subdirs=scope,
            )
            self.signals.transfer_line.emit(
                f"🔄 Rescan complete: +{summary.get('added_records', 0)} indexed, "
                f"{summary.get('errors', 0)} errors"
            )
        except Exception:
            logging.warning("Post-import reconcile failed.", exc_info=True)

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
