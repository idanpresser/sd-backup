"""
SQLite Database Manager for SD-FastBackup.
Maintains state catalog, volume records, and transfer manifests with WAL mode enabled.
"""
import sqlite3
import os
from typing import Optional, List, Dict, Any


class DatabaseManager:
    """Thread-safe SQLite Manager operating on the target backup directory."""

    def __init__(self, target_dir: str):
        self.target_dir = os.path.abspath(target_dir)
        os.makedirs(self.target_dir, exist_ok=True)
        self.db_path = os.path.join(self.target_dir, ".sd_backup_catalog.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS volumes (
                    volume_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    volume_serial TEXT UNIQUE,
                    volume_label TEXT,
                    last_scanned_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS file_catalog (
                    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_hash TEXT UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    date_taken DATETIME NOT NULL,
                    date_taken_source TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transfer_manifest (
                    transfer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_hash TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    destination_path TEXT NOT NULL,
                    copy_status TEXT CHECK(copy_status IN ('PENDING', 'COPIED', 'FAILED', 'DUPLICATE_SKIPPED')),
                    transferred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(composite_hash) REFERENCES file_catalog(composite_hash)
                );
            """)

    def register_volume(self, volume_serial: str, volume_label: str):
        """Registers or updates a scanned SD card volume record."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO volumes (volume_serial, volume_label, last_scanned_timestamp)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(volume_serial) DO UPDATE SET
                    volume_label = excluded.volume_label,
                    last_scanned_timestamp = CURRENT_TIMESTAMP
            """, (volume_serial, volume_label))

    def register_file(self, composite_hash: str, filename: str, rel_path: str, size: int, date_taken: str, source: str):
        """Registers a discovered file into the file_catalog table."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO file_catalog (composite_hash, original_filename, relative_path, file_size_bytes, date_taken, date_taken_source)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(composite_hash) DO NOTHING
            """, (composite_hash, filename, rel_path, size, date_taken, source))

    def update_transfer_status(self, composite_hash: str, source_path: str, dest_path: str, status: str):
        """Records or updates a transfer attempt in transfer_manifest."""
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO transfer_manifest (composite_hash, source_path, destination_path, copy_status)
                VALUES (?, ?, ?, ?)
            """, (composite_hash, source_path, dest_path, status))

    def is_file_copied(self, composite_hash: str) -> bool:
        """Returns True if composite_hash has status 'COPIED' in transfer_manifest."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM transfer_manifest 
                WHERE composite_hash = ? AND copy_status = 'COPIED' 
                LIMIT 1
            """, (composite_hash,))
            return cursor.fetchone() is not None

    def get_transfer_status(self, composite_hash: str) -> Optional[str]:
        """Returns the latest copy_status for a composite_hash, or None if not found."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT copy_status FROM transfer_manifest 
                WHERE composite_hash = ? 
                ORDER BY transfer_id DESC 
                LIMIT 1
            """, (composite_hash,))
            row = cursor.fetchone()
            return row["copy_status"] if row else None

    def get_failed_transfers(self) -> List[Dict[str, Any]]:
        """Returns all transfer manifest entries that failed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT transfer_id, composite_hash, source_path, destination_path, copy_status, transferred_at 
                FROM transfer_manifest 
                WHERE copy_status = 'FAILED'
            """)
            return [dict(row) for row in cursor.fetchall()]

    def checkpoint(self):
        """Runs a WAL checkpoint to flush WAL logs to disk."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
