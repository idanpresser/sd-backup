"""
Folder Indexing Engine for SD-FastBackup.
Indexes arbitrary existing media folders in-place to create or update .sd_backup_catalog.db
for consumption by QuickImageCullLAN and internal catalog tools.
"""
import os
import logging
from typing import Dict, Any, Optional, Callable, List

from core.db import DatabaseManager, register_metadata_batched
from core.metadata import MetadataExtractor
from utils.path_formatter import normalize_win_path
from utils.media_filter import is_media_file, is_blacklisted_system_file


class FolderIndexer:
    """Indexes an existing media folder in-place without moving, copying, or renaming files."""

    @staticmethod
    def discover_media_files(root_dir: str, include_subdirs: bool = True) -> List[str]:
        """Discovers all cullable media files in root_dir."""
        norm_root = normalize_win_path(os.path.abspath(root_dir))
        media_files = []

        if not os.path.exists(norm_root):
            return []

        if include_subdirs:
            for root, dirs, files in os.walk(norm_root):
                # Filter out hidden/system subfolders
                dirs[:] = [
                    d for d in dirs 
                    if not d.startswith('.') 
                    and d.lower() not in ('.sd_backup_logs', '$recycle.bin', 'system volume information')
                ]
                for f in files:
                    if f.startswith('.') or f.endswith(('.db', '.db-wal', '.db-shm', '.log')):
                        continue
                    full_p = normalize_win_path(os.path.join(root, f))
                    if is_media_file(full_p):
                        media_files.append(full_p)
        else:
            try:
                for f in os.listdir(norm_root):
                    if f.startswith('.') or f.endswith(('.db', '.db-wal', '.db-shm', '.log')):
                        continue
                    full_p = normalize_win_path(os.path.join(norm_root, f))
                    if os.path.isfile(full_p) and is_media_file(full_p):
                        media_files.append(full_p)
            except Exception as e:
                logging.warning(f"Error listing directory '{norm_root}': {e}")

        return media_files

    @classmethod
    def index_folder(
        cls,
        root_dir: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        force_reextract: bool = False,
        include_subdirs: bool = True
    ) -> Dict[str, Any]:
        """
        Indexes all media files in root_dir in-place into .sd_backup_catalog.db.

        Args:
            root_dir: Directory containing images/videos to index.
            progress_callback: Callback function receiving progress dict.
            is_cancelled: Callback function returning True if operation should cancel.
            force_reextract: If True, re-extracts full EXIF/MediaInfo even if already in catalog.
            include_subdirs: If True, traverses subdirectories recursively.

        Returns:
            Dict containing summary stats of the indexing run.
        """
        norm_root = normalize_win_path(os.path.abspath(root_dir))
        if not os.path.exists(norm_root):
            raise FileNotFoundError(f"Target folder does not exist: {norm_root}")

        db = DatabaseManager(norm_root)
        # Signal external readers (e.g. QuickImageCullLAN) that a write operation is active
        db.set_in_progress(True)

        added_count = 0
        skipped_count = 0
        metadata_count = 0
        pending_metadata = []      # (file_path, composite_hash, filename) for the batched pass
        errors = 0
        cancelled = False

        try:
            # 1. Discover media files
            if progress_callback:
                progress_callback({
                    "status": "DISCOVERING",
                    "current": 0,
                    "total": 0,
                    "message": "Discovering media files..."
                })

            files = cls.discover_media_files(norm_root, include_subdirs=include_subdirs)
            total_files = len(files)

            # 2. Pre-fetch existing catalog hashes and metadata state
            existing_catalog = set()
            existing_metadata = set()

            # Closed explicitly: `with <sqlite connection>` commits but does not close, so
            # the handle would stay bound in this frame — holding the WAL lock — until
            # after the finalize() in the finally block, leaving -wal/-shm sidecars behind.
            conn = db._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT composite_hash FROM file_catalog")
                existing_catalog = {row["composite_hash"] for row in cursor.fetchall()}

                if not force_reextract:
                    cursor.execute("""
                        SELECT composite_hash FROM file_metadata
                        WHERE raw_json IS NOT NULL AND raw_json != '{}' AND camera_make IS NOT NULL
                    """)
                    existing_metadata = {row["composite_hash"] for row in cursor.fetchall()}
            finally:
                conn.close()

            # 3. Process files
            for idx, full_p in enumerate(files, start=1):
                if is_cancelled and is_cancelled():
                    cancelled = True
                    break

                fname = os.path.basename(full_p)
                rel_p = normalize_win_path(os.path.relpath(full_p, norm_root))

                try:
                    comp_hash, size, dt_taken, source_type = MetadataExtractor.compute_composite_hash(full_p)
                    dt_iso = dt_taken.isoformat()

                    is_new_file = comp_hash not in existing_catalog

                    if is_new_file:
                        db.register_file(
                            composite_hash=comp_hash,
                            filename=fname,
                            rel_path=rel_p,
                            size=size,
                            date_taken=dt_iso,
                            source=source_type,
                            destination_filename=fname,
                            target_relative_path=rel_p
                        )
                        db.update_transfer_status(comp_hash, full_p, full_p, "COPIED")
                        existing_catalog.add(comp_hash)
                        added_count += 1
                    else:
                        # Ensure target_relative_path is populated/updated if needed
                        db.register_file(
                            composite_hash=comp_hash,
                            filename=fname,
                            rel_path=rel_p,
                            size=size,
                            date_taken=dt_iso,
                            source=source_type,
                            destination_filename=fname,
                            target_relative_path=rel_p
                        )
                        skipped_count += 1

                    # Queue extended metadata for the batched ExifTool pass below.
                    if force_reextract or comp_hash not in existing_metadata:
                        pending_metadata.append((full_p, comp_hash, fname))
                        existing_metadata.add(comp_hash)

                except Exception as file_err:
                    logging.error(f"Error indexing file '{full_p}': {file_err}")
                    errors += 1

                if progress_callback:
                    progress_callback({
                        "status": "INDEXING",
                        "current": idx,
                        "total": total_files,
                        "current_file": fname,
                        "relative_path": rel_p,
                        "added": added_count,
                        "skipped": skipped_count,
                        "metadata_extracted": metadata_count,
                        "errors": errors
                    })

            # One ExifTool invocation per chunk instead of one per indexed file.
            def _meta_progress(done, total):
                if progress_callback:
                    progress_callback({
                        "status": "METADATA",
                        "current": done,
                        "total": total,
                        "current_file": f"Extracting metadata ({done}/{total})",
                        "relative_path": "",
                        "added": added_count,
                        "skipped": skipped_count,
                        "metadata_extracted": done,
                        "errors": errors
                    })

            metadata_count = register_metadata_batched(
                db, pending_metadata, progress_callback=_meta_progress
            )

            # Checkpoint and bump generation if new data was written
            if added_count > 0 or metadata_count > 0:
                db.bump_generation()

        finally:
            # Leave the catalog quiescent for external readers (flush WAL, clear in_progress)
            db.finalize()

        return {
            "total_discovered": len(files) if 'files' in locals() else 0,
            "added_records": added_count,
            "skipped_records": skipped_count,
            "metadata_extracted": metadata_count,
            "errors": errors,
            "cancelled": cancelled
        }
