"""
Blacklist Cleaner Helper for SD-FastBackup.
Purges blacklisted non-media system/database files from backup disk directories and SQLite catalog.
Handles read-only file permissions on camera system index files.
"""
import os
import sys
import stat
import sqlite3
import logging
from typing import Optional, Dict, Any, List
from utils.path_formatter import normalize_win_path
from utils.media_filter import is_blacklisted_system_file


def _remove_readonly(func, path, excinfo):
    """Clear the read-only attribute and retry the remove."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def clean_blacklisted_files_in_backup(root_dir: str) -> Dict[str, Any]:
    """
    Scans target backup root directory for blacklisted non-media system files,
    deletes them from disk, and removes their SQLite database entries.
    
    Args:
        root_dir: Target backup root directory (where .sd_backup_catalog.db lives)
        
    Returns:
        Dict with summary counts: scanned_count, deleted_count, db_removed_count, errors
    """
    norm_root = normalize_win_path(os.path.abspath(root_dir))
    if not os.path.exists(norm_root):
        raise FileNotFoundError(f"Backup root directory does not exist: {norm_root}")

    db_path = os.path.join(norm_root, ".sd_backup_catalog.db")
    conn: Optional[sqlite3.Connection] = None
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")

    blacklisted_paths: List[str] = []

    # 1. Walk root_dir on disk for any blacklisted system files
    scanned_count = 0
    for root, _, files in os.walk(norm_root):
        for fname in files:
            if fname.startswith('.'):
                continue
            scanned_count += 1
            full_p = normalize_win_path(os.path.join(root, fname))
            if is_blacklisted_system_file(full_p):
                if full_p not in blacklisted_paths:
                    blacklisted_paths.append(full_p)

    # 2. Query SQLite catalog for any blacklisted entries
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT destination_path FROM transfer_manifest")
        for row in cursor.fetchall():
            dest_p = normalize_win_path(row["destination_path"])
            if dest_p and is_blacklisted_system_file(dest_p):
                if dest_p not in blacklisted_paths:
                    blacklisted_paths.append(dest_p)

    deleted_count = 0
    db_removed_count = 0
    errors = 0

    # 3. Delete files from disk and update SQLite catalog
    for file_p in blacklisted_paths:
        norm_p = normalize_win_path(file_p)

        # Remove from disk
        if os.path.exists(norm_p):
            try:
                # Clear read-only attribute if set
                os.chmod(norm_p, stat.S_IWRITE | stat.S_IWUSR)
                os.remove(norm_p)
                deleted_count += 1
            except Exception as e:
                logging.error(f"Error removing blacklisted file '{norm_p}': {e}")
                errors += 1
                continue
        else:
            deleted_count += 1

        # Remove from SQLite DB
        if conn:
            try:
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT composite_hash FROM transfer_manifest WHERE destination_path = ?",
                    (norm_p,)
                )
                rows = cursor.fetchall()
                hashes = [r["composite_hash"] for r in rows]

                cursor.execute(
                    "DELETE FROM transfer_manifest WHERE destination_path = ?",
                    (norm_p,)
                )
                db_removed_count += cursor.rowcount

                for h in hashes:
                    cursor.execute("DELETE FROM file_catalog WHERE composite_hash = ?", (h,))
                    cursor.execute("DELETE FROM transfer_manifest WHERE composite_hash = ?", (h,))

            except Exception as e:
                logging.error(f"Error removing SQLite records for '{norm_p}': {e}")
                errors += 1

    if conn:
        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        conn.close()

    return {
        "scanned_count": scanned_count,
        "deleted_count": deleted_count,
        "db_removed_count": db_removed_count,
        "errors": errors
    }
