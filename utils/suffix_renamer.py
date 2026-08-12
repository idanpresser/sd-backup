"""
Suffix Renamer Helper for SD-FastBackup.
Renames file suffixes on disk and updates the target SQLite database catalog (.sd_backup_catalog.db).
"""
import os
import sys
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from utils.path_formatter import normalize_win_path


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
        file_list_path: Optional path to a text file listing specific target files
        
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

    # 1. Determine list of files to rename
    if file_list_path and os.path.exists(file_list_path):
        with open(file_list_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                cleaned = line.strip().strip('"\'')
                if cleaned and not cleaned.startswith('#'):
                    # Normalize path relative to root_dir if needed
                    full_p = cleaned if os.path.isabs(cleaned) else os.path.join(norm_root, cleaned)
                    target_files.append(normalize_win_path(full_p))
    else:
        # Scan SQLite database if present, or search filesystem root_dir
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

        # Also walk root_dir on disk for any files matching old_suffix
        for root, _, files in os.walk(norm_root):
            for fname in files:
                if old_suffix in fname and not fname.startswith('.'):
                    full_p = normalize_win_path(os.path.join(root, fname))
                    if full_p not in target_files:
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

        # Rename file on disk if present
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
            # File was already renamed on disk previously
            renamed_count += 1

        # Update SQLite database catalog
        if conn:
            try:
                conn.execute(
                    "UPDATE transfer_manifest SET destination_path = ? WHERE destination_path = ?",
                    (new_path, norm_old_path)
                )
                db_updated_count += 1
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
