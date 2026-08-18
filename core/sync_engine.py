"""
DB-Disk Synchronization Engine for SD-FastBackup.
Calculates preview diffs between target disk storage and SQLite catalog,
purges stale records for missing files, and indexes untracked media files.
"""
import os
import sqlite3
import logging
from typing import Dict, Any, List
from utils.path_formatter import normalize_win_path
from utils.media_filter import is_blacklisted_system_file
from core.metadata import MetadataExtractor
from core.db import DatabaseManager


def calculate_sync_diff(root_dir: str) -> Dict[str, Any]:
    """
    Scans backup root directory and compares against SQLite catalog.

    Returns dict with:
        'missing_records': List of catalog records whose file is no longer present on disk
        'uncataloged_files': List of media files present on disk that have no catalog record
    """
    norm_root = normalize_win_path(os.path.abspath(root_dir))
    if not os.path.exists(norm_root):
        raise FileNotFoundError(f"Backup root directory does not exist: {norm_root}")

    db = DatabaseManager(norm_root)

    missing_records: List[Dict[str, Any]] = []
    uncataloged_files: List[Dict[str, Any]] = []

    # 1. Inspect DB for missing files on disk
    known_disk_paths = set()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT fc.composite_hash, fc.original_filename, fc.relative_path, fc.destination_filename, fc.target_relative_path, tm.destination_path 
            FROM file_catalog fc
            LEFT JOIN transfer_manifest tm ON fc.composite_hash = tm.composite_hash
        """)
        rows = cursor.fetchall()
        for r in rows:
            dest_p = normalize_win_path(r["destination_path"]) if r["destination_path"] else ""
            if not dest_p and ("target_relative_path" in r.keys() and r["target_relative_path"]):
                dest_p = normalize_win_path(os.path.join(norm_root, r["target_relative_path"]))
            elif not dest_p and r["relative_path"]:
                dest_p = normalize_win_path(os.path.join(norm_root, r["relative_path"]))

            if dest_p:
                known_disk_paths.add(dest_p)
                if not os.path.exists(dest_p):
                    missing_records.append({
                        "composite_hash": r["composite_hash"],
                        "original_filename": r["original_filename"],
                        "destination_path": dest_p,
                        "relative_path": r["relative_path"]
                    })

    # 2. Walk disk to find uncataloged files
    cataloged_hashes = set()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT composite_hash FROM file_catalog")
        for r in cursor.fetchall():
            cataloged_hashes.add(r["composite_hash"])

    for root, _, files in os.walk(norm_root):
        for fname in files:
            if fname.startswith('.') or fname.endswith('.db') or fname.endswith('.db-wal') or fname.endswith('.db-shm'):
                continue
            full_p = normalize_win_path(os.path.join(root, fname))
            if is_blacklisted_system_file(full_p):
                continue

            # Compute hash to check if already in catalog
            try:
                comp_hash, size, dt_taken, source_type = MetadataExtractor.compute_composite_hash(full_p)
                if comp_hash not in cataloged_hashes and full_p not in known_disk_paths:
                    rel_p = normalize_win_path(os.path.relpath(full_p, norm_root))
                    uncataloged_files.append({
                        "file_path": full_p,
                        "relative_path": rel_p,
                        "composite_hash": comp_hash,
                        "file_size": size,
                        "date_taken": dt_taken,
                        "source_type": source_type
                    })
            except Exception as e:
                logging.warning(f"Could not calculate hash for file '{full_p}': {e}")

    return {
        "missing_records": missing_records,
        "uncataloged_files": uncataloged_files
    }


def execute_sync(
    root_dir: str,
    remove_missing: bool = True,
    add_uncataloged: bool = True,
    uncataloged_action: str = "ADD_TO_DB"
) -> Dict[str, int]:
    """
    Executes synchronization actions between disk storage and SQLite catalog based on options.

    Args:
        root_dir: Target backup directory path
        remove_missing: If True, purges catalog records for missing disk files
        add_uncataloged: Backwards compatibility boolean (if True and uncataloged_action default, adds to DB)
        uncataloged_action: Action for untracked disk files ("ADD_TO_DB", "DELETE_FROM_DISK", "IGNORE")

    Returns dict with summary counts:
        'removed_records': int
        'added_records': int
        'deleted_disk_files': int
        'errors': int
    """
    norm_root = normalize_win_path(os.path.abspath(root_dir))
    diff = calculate_sync_diff(norm_root)
    db = DatabaseManager(norm_root)

    removed_count = 0
    added_count = 0
    deleted_disk_count = 0
    errors = 0

    # 1. Remove missing records from SQLite DB
    if remove_missing and diff["missing_records"]:
        with db._get_connection() as conn:
            cursor = conn.cursor()
            for rec in diff["missing_records"]:
                h = rec["composite_hash"]
                try:
                    cursor.execute("DELETE FROM transfer_manifest WHERE composite_hash = ?", (h,))
                    cursor.execute("DELETE FROM file_metadata WHERE composite_hash = ?", (h,))
                    cursor.execute("DELETE FROM file_catalog WHERE composite_hash = ?", (h,))
                    removed_count += 1
                except Exception as e:
                    logging.error(f"Error purging missing record '{h}': {e}")
                    errors += 1
            conn.commit()

    # Determine active action for uncataloged files
    effective_action = uncataloged_action
    if not add_uncataloged and uncataloged_action == "ADD_TO_DB":
        effective_action = "IGNORE"

    # 2. Process uncataloged files on disk
    if diff["uncataloged_files"] and effective_action != "IGNORE":
        for item in diff["uncataloged_files"]:
            full_p = item["file_path"]

            if effective_action == "ADD_TO_DB":
                comp_hash = item["composite_hash"]
                fname = os.path.basename(full_p)
                rel_p = item["relative_path"]
                size = item["file_size"]
                dt_iso = item["date_taken"].isoformat()
                src = item["source_type"]

                try:
                    db.register_file(
                        comp_hash, 
                        fname, 
                        rel_p, 
                        size, 
                        dt_iso, 
                        src,
                        destination_filename=fname,
                        target_relative_path=rel_p
                    )
                    db.update_transfer_status(comp_hash, full_p, full_p, "COPIED")
                    meta = MetadataExtractor.extract_full_metadata(full_p)
                    db.register_metadata(comp_hash, fname, meta)
                    added_count += 1
                except Exception as e:
                    logging.error(f"Error adding uncataloged file '{full_p}' to DB: {e}")
                    errors += 1

            elif effective_action == "DELETE_FROM_DISK":
                if os.path.exists(full_p):
                    try:
                        import stat
                        os.chmod(full_p, stat.S_IWRITE | stat.S_IWUSR)
                        os.remove(full_p)
                        deleted_disk_count += 1
                    except Exception as e:
                        logging.error(f"Error deleting uncataloged file '{full_p}' from disk: {e}")
                        errors += 1

    db.checkpoint()

    return {
        "removed_records": removed_count,
        "added_records": added_count,
        "deleted_disk_files": deleted_disk_count,
        "errors": errors
    }

