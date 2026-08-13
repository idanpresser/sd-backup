"""
Consolidated Maintenance Engine for SD-FastBackup.
Combines suffix renaming and blacklisted system file purging across target directories and SQLite catalog.
"""
import os
import sys
import stat
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from utils.path_formatter import normalize_win_path
from utils.media_filter import is_blacklisted_system_file


def _remove_readonly(func, path, excinfo):
    """Clear the read-only attribute and retry the remove operation."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def rename_suffix_in_backup(
    root_dir: str,
    old_suffix: str,
    new_suffix: str,
    file_list_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Renames file suffixes in target backup directory and updates SQLite catalog.

    Args:
        root_dir: Target backup root directory (where .sd_backup_catalog.db lives)
        old_suffix: Old suffix substring to replace (e.g. "AnatKP(C)")
        new_suffix: New replacement suffix string (e.g. "IdanPresser(C)")
        file_list_path: Optional path to a text file listing specific target files/basenames

    Returns:
        Dict with summary counts: scanned_count, renamed_count, db_updated_count, errors
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

    target_files: List[str] = []

    # Build a lookup of all files on disk under norm_root for fast resolution of basenames
    file_disk_map: Dict[str, str] = {}
    for root, _, files in os.walk(norm_root):
        for fname in files:
            if not fname.startswith('.'):
                norm_full = normalize_win_path(os.path.join(root, fname))
                file_disk_map[fname] = norm_full

    # 1. Determine list of target files to rename
    if file_list_path and os.path.exists(file_list_path):
        with open(file_list_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                cleaned = line.strip().strip('"\'')
                if not cleaned or cleaned.startswith('#'):
                    continue

                norm_cleaned = normalize_win_path(cleaned)
                basename = os.path.basename(norm_cleaned)
                resolved_path = ""

                if os.path.isabs(norm_cleaned) and os.path.exists(norm_cleaned):
                    resolved_path = norm_cleaned
                elif os.path.exists(os.path.join(norm_root, norm_cleaned)):
                    resolved_path = normalize_win_path(os.path.join(norm_root, norm_cleaned))
                elif conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT destination_path FROM transfer_manifest WHERE destination_path LIKE ?",
                        (f"%{basename}",)
                    )
                    row = cursor.fetchone()
                    if row and row["destination_path"]:
                        resolved_path = normalize_win_path(row["destination_path"])

                if not resolved_path and basename in file_disk_map:
                    resolved_path = file_disk_map[basename]

                if not resolved_path:
                    resolved_path = normalize_win_path(os.path.join(norm_root, norm_cleaned))

                if resolved_path not in target_files:
                    target_files.append(resolved_path)
    else:
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT destination_path FROM transfer_manifest WHERE destination_path LIKE ?",
                (f"%{old_suffix}%",)
            )
            for row in cursor.fetchall():
                dest_p = normalize_win_path(row["destination_path"])
                if dest_p not in target_files:
                    target_files.append(dest_p)

        for fname, full_p in file_disk_map.items():
            if old_suffix in fname and full_p not in target_files:
                target_files.append(full_p)

    renamed_count = 0
    db_updated_count = 0
    errors = 0

    # 2. Execute file renaming and DB updates
    for old_path in target_files:
        norm_old_path = normalize_win_path(old_path)
        dir_name = os.path.dirname(norm_old_path)
        base_name = os.path.basename(norm_old_path)

        if old_suffix not in base_name:
            continue

        new_base_name = base_name.replace(old_suffix, new_suffix)
        new_path = normalize_win_path(os.path.join(dir_name, new_base_name))

        if os.path.exists(norm_old_path):
            try:
                os.makedirs(dir_name, exist_ok=True)
                os.rename(norm_old_path, new_path)
                renamed_count += 1
            except Exception as e:
                logging.error(f"Error renaming file '{norm_old_path}' to '{new_path}': {e}")
                errors += 1
                continue
        elif os.path.exists(new_path):
            renamed_count += 1

        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE transfer_manifest SET destination_path = ? WHERE destination_path = ?",
                    (new_path, norm_old_path)
                )
                if cursor.rowcount > 0:
                    db_updated_count += cursor.rowcount
                else:
                    cursor.execute(
                        "UPDATE transfer_manifest SET destination_path = ? WHERE destination_path LIKE ?",
                        (new_path, f"%{base_name}")
                    )
                    if cursor.rowcount > 0:
                        db_updated_count += cursor.rowcount
            except Exception as e:
                logging.error(f"Error updating SQLite catalog for '{norm_old_path}': {e}")
                errors += 1

    if conn:
        conn.commit()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass
        conn.close()

    return {
        "scanned_count": len(target_files),
        "renamed_count": renamed_count,
        "db_updated_count": db_updated_count,
        "errors": errors
    }


def clean_blacklisted_files_in_backup(root_dir: str) -> Dict[str, Any]:
    """
    Scans target backup root directory for blacklisted non-media system files,
    deletes them from disk, and removes their SQLite database entries.
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

    for file_p in blacklisted_paths:
        norm_p = normalize_win_path(file_p)

        if os.path.exists(norm_p):
            try:
                os.chmod(norm_p, stat.S_IWRITE | stat.S_IWUSR)
                os.remove(norm_p)
                deleted_count += 1
            except Exception as e:
                logging.error(f"Error removing blacklisted file '{norm_p}': {e}")
                errors += 1
                continue
        else:
            deleted_count += 1

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
                    cursor.execute("DELETE FROM file_metadata WHERE composite_hash = ?", (h,))
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
