"""
SQLite Database Manager for SD-FastBackup.
Maintains state catalog, volume records, and transfer manifests with WAL mode enabled.
"""
import sqlite3
import os
import gc
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

from utils.path_formatter import normalize_win_path, is_safe_relative_path


def register_metadata_batched(
    db: "DatabaseManager",
    targets: List[tuple],
    chunk_size: int = 200,
    progress_callback=None,
    camera_make_fallback: Optional[str] = None,
) -> int:
    """Extract and store extended metadata for many files, one ExifTool call per chunk.

    `targets` is a list of (file_path, composite_hash, filename). Extracting per file
    spawned ExifTool once per file (~430ms of interpreter startup each), which dominated
    every path that catalogs metadata — imports, reconciles, and folder indexing alike.
    Each chunk's catalog writes also share a single connection and transaction.

    `progress_callback(done, total)` is invoked after each chunk. Returns the number of
    files whose metadata was stored.
    """
    from core.metadata import MetadataExtractor

    if not targets:
        return 0

    total = len(targets)
    done = 0
    stored = 0

    for start in range(0, total, chunk_size):
        chunk = targets[start:start + chunk_size]
        try:
            results = MetadataExtractor.extract_full_metadata_batch(
                [t[0] for t in chunk], chunk_size=chunk_size
            )
        except Exception:
            logging.warning("Batched metadata extraction failed for a chunk.", exc_info=True)
            results = {}

        try:
            with db.batch() as conn:
                for file_path, composite_hash, filename in chunk:
                    meta = results.get(file_path)
                    if not meta:
                        continue
                    if camera_make_fallback:
                        meta["camera_make"] = meta.get("camera_make") or camera_make_fallback
                    db.register_metadata(composite_hash, filename, meta, conn=conn)
                    stored += 1
        except Exception:
            logging.warning("Could not persist a metadata chunk.", exc_info=True)

        done += len(chunk)
        if progress_callback:
            try:
                progress_callback(done, total)
            except Exception:
                pass

    return stored


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
                    destination_filename TEXT,
                    target_relative_path TEXT,
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

                CREATE TABLE IF NOT EXISTS file_metadata (
                    metadata_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    composite_hash TEXT UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    camera_make TEXT,
                    camera_model TEXT,
                    lens_model TEXT,
                    serial_number TEXT,
                    iso INTEGER,
                    aperture TEXT,
                    shutter_speed TEXT,
                    focal_length TEXT,
                    white_balance TEXT,
                    width INTEGER,
                    height INTEGER,
                    aspect_ratio TEXT,
                    color_space TEXT,
                    video_codec TEXT,
                    container_format TEXT,
                    frame_rate REAL,
                    duration_seconds REAL,
                    bitrate INTEGER,
                    audio_codec TEXT,
                    audio_channels INTEGER,
                    audio_sample_rate INTEGER,
                    latitude REAL,
                    longitude REAL,
                    altitude REAL,
                    raw_json TEXT,
                    FOREIGN KEY(composite_hash) REFERENCES file_catalog(composite_hash)
                );

                -- Published contract metadata for external consumers (e.g. the culler).
                -- 'generation' is a monotonic counter bumped on every import/reconcile so
                -- a consumer can cheaply detect that the catalog changed; 'last_import'
                -- is the wall-clock time of the last bump.
                CREATE TABLE IF NOT EXISTS catalog_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_file_catalog_hash ON file_catalog(composite_hash);
                CREATE INDEX IF NOT EXISTS idx_manifest_hash ON transfer_manifest(composite_hash);
                CREATE INDEX IF NOT EXISTS idx_manifest_status ON transfer_manifest(copy_status);
                CREATE INDEX IF NOT EXISTS idx_metadata_hash ON file_metadata(composite_hash);
            """)
            # Schema Migration: Add missing columns to file_catalog if upgrading from legacy DB
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(file_catalog);")
            columns = [row["name"] for row in cursor.fetchall()]
            if "destination_filename" not in columns:
                conn.execute("ALTER TABLE file_catalog ADD COLUMN destination_filename TEXT;")
            if "target_relative_path" not in columns:
                conn.execute("ALTER TABLE file_catalog ADD COLUMN target_relative_path TEXT;")

            # Automatically purge legacy DUPLICATE_SKIPPED entries from transfer_manifest
            conn.execute("DELETE FROM transfer_manifest WHERE copy_status = 'DUPLICATE_SKIPPED';")

    @contextmanager
    def batch(self):
        """Yields one connection for a burst of writes, committed once at the end.

        Each write method otherwise opens its own connection (re-running the WAL and
        foreign-key PRAGMAs every time), which cost ~80ms per file across the three
        writes the transfer path makes — far more than the transfer itself in move mode.
        Pass the yielded connection as `conn=` to keep a whole loop on one transaction.

        Rolls back if the body raises, so a failed session leaves no partial rows.
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _write(self, conn: Optional[sqlite3.Connection]):
        """Uses the caller's batch connection when given, else a one-shot connection."""
        if conn is not None:
            yield conn          # the batch owns the commit
        else:
            with self._get_connection() as own:
                yield own

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

    def register_file(
        self, 
        composite_hash: str, 
        filename: str, 
        rel_path: str, 
        size: int, 
        date_taken: str, 
        source: str,
        destination_filename: Optional[str] = None,
        target_relative_path: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None
    ):
        """Registers a discovered or transferred file into the file_catalog table.

        Pass `conn` from DatabaseManager.batch() to keep a loop of registrations on a
        single connection and transaction. The path guard below applies either way —
        this stays the one write path into file_catalog.
        """
        # Guard the single catalog write path: never persist a non-archive-relative
        # target path. The culler joins archive_root / target_relative_path and rejects
        # absolute/drive-lettered/UNC/'..'-escaping paths, so storing one here would make
        # the file silently un-cullable (or enable a path escape). Normalize, then drop to
        # NULL if it is not safe rather than poisoning the catalog. See sd_backup-vmp.
        if target_relative_path is not None:
            normalized_rel = normalize_win_path(target_relative_path)
            if is_safe_relative_path(normalized_rel):
                target_relative_path = normalized_rel
            else:
                logging.warning(
                    f"register_file: unsafe target_relative_path '{target_relative_path}' "
                    f"for '{filename}'; storing NULL to keep the catalog archive-relative."
                )
                target_relative_path = None

        with self._write(conn) as c:
            c.execute("""
                INSERT INTO file_catalog (
                    composite_hash, original_filename, relative_path, 
                    destination_filename, target_relative_path, 
                    file_size_bytes, date_taken, date_taken_source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(composite_hash) DO UPDATE SET
                    destination_filename = COALESCE(excluded.destination_filename, file_catalog.destination_filename),
                    target_relative_path = COALESCE(excluded.target_relative_path, file_catalog.target_relative_path)
            """, (composite_hash, filename, rel_path, destination_filename, target_relative_path, size, date_taken, source))

    def register_metadata(self, composite_hash: str, filename: str, metadata: Dict[str, Any],
                          conn: Optional[sqlite3.Connection] = None):
        """Registers or updates extended image/video metadata in file_metadata table."""
        with self._write(conn) as c:
            c.execute("""
                INSERT INTO file_metadata (
                    composite_hash, original_filename, camera_make, camera_model, lens_model, serial_number,
                    iso, aperture, shutter_speed, focal_length, white_balance, width, height, aspect_ratio,
                    color_space, video_codec, container_format, frame_rate, duration_seconds, bitrate,
                    audio_codec, audio_channels, audio_sample_rate, latitude, longitude, altitude, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(composite_hash) DO UPDATE SET
                    original_filename=excluded.original_filename,
                    camera_make=excluded.camera_make,
                    camera_model=excluded.camera_model,
                    lens_model=excluded.lens_model,
                    serial_number=excluded.serial_number,
                    iso=excluded.iso,
                    aperture=excluded.aperture,
                    shutter_speed=excluded.shutter_speed,
                    focal_length=excluded.focal_length,
                    white_balance=excluded.white_balance,
                    width=excluded.width,
                    height=excluded.height,
                    aspect_ratio=excluded.aspect_ratio,
                    color_space=excluded.color_space,
                    video_codec=excluded.video_codec,
                    container_format=excluded.container_format,
                    frame_rate=excluded.frame_rate,
                    duration_seconds=excluded.duration_seconds,
                    bitrate=excluded.bitrate,
                    audio_codec=excluded.audio_codec,
                    audio_channels=excluded.audio_channels,
                    audio_sample_rate=excluded.audio_sample_rate,
                    latitude=excluded.latitude,
                    longitude=excluded.longitude,
                    altitude=excluded.altitude,
                    raw_json=excluded.raw_json
            """, (
                composite_hash, filename,
                metadata.get("camera_make"), metadata.get("camera_model"), metadata.get("lens_model"), metadata.get("serial_number"),
                metadata.get("iso"), metadata.get("aperture"), metadata.get("shutter_speed"), metadata.get("focal_length"), metadata.get("white_balance"),
                metadata.get("width"), metadata.get("height"), metadata.get("aspect_ratio"), metadata.get("color_space"),
                metadata.get("video_codec"), metadata.get("container_format"), metadata.get("frame_rate"), metadata.get("duration_seconds"), metadata.get("bitrate"),
                metadata.get("audio_codec"), metadata.get("audio_channels"), metadata.get("audio_sample_rate"),
                metadata.get("latitude"), metadata.get("longitude"), metadata.get("altitude"),
                metadata.get("raw_json", "{}")
            ))

    def get_metadata(self, composite_hash: str) -> Optional[Dict[str, Any]]:
        """Returns metadata for a given composite_hash, or None if not found."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_metadata WHERE composite_hash = ?", (composite_hash,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_transfer_status(self, composite_hash: str, source_path: str, dest_path: str, status: str,
                               conn: Optional[sqlite3.Connection] = None):
        """Records or updates a transfer attempt in transfer_manifest."""
        with self._write(conn) as c:
            c.execute("""
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

    def delete_file_record(self, composite_hash: str):
        """Deletes a file and its associated metadata/manifest entries by composite_hash."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transfer_manifest WHERE composite_hash = ?", (composite_hash,))
            cursor.execute("DELETE FROM file_metadata WHERE composite_hash = ?", (composite_hash,))
            cursor.execute("DELETE FROM file_catalog WHERE composite_hash = ?", (composite_hash,))

    def backfill_missing_metadata(self, force_reextract: bool = False) -> int:
        """
        Scans file_catalog entries and extracts EXIF/MediaInfo metadata.
        Resolves files located under target_dir even if destination_path has stale drive letters.

        Args:
            force_reextract: If True, re-extracts metadata for ALL cataloged files.
        """
        from core.metadata import MetadataExtractor
        from utils.path_formatter import normalize_win_path

        sql = """
            SELECT fc.composite_hash, fc.original_filename, fc.relative_path, fc.destination_filename, fc.target_relative_path, tm.destination_path
            FROM file_catalog fc
            LEFT JOIN transfer_manifest tm ON fc.composite_hash = tm.composite_hash
        """
        if not force_reextract:
            sql += """
                LEFT JOIN file_metadata fm ON fc.composite_hash = fm.composite_hash
                WHERE fm.composite_hash IS NULL OR fm.raw_json = '{}' OR fm.raw_json IS NULL OR fm.camera_make IS NULL
            """

        missing_items = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            for r in rows:
                missing_items.append({
                    "composite_hash": r["composite_hash"],
                    "original_filename": r["original_filename"],
                    "relative_path": r["relative_path"],
                    "destination_filename": r["destination_filename"] if "destination_filename" in r.keys() else None,
                    "target_relative_path": r["target_relative_path"] if "target_relative_path" in r.keys() else None,
                    "destination_path": r["destination_path"]
                })

        if not missing_items:
            return 0

        disk_file_index = None
        norm_target = normalize_win_path(os.path.abspath(self.target_dir))

        backfilled_count = 0
        pending = []          # (file_path, composite_hash, filename) for the batched pass
        for item in missing_items:
            h_val = item["composite_hash"]
            fname = item["original_filename"]
            dest_p = normalize_win_path(item["destination_path"]) if item.get("destination_path") else ""
            target_rel_p = normalize_win_path(item["target_relative_path"]) if item.get("target_relative_path") else ""
            rel_p = normalize_win_path(item["relative_path"]) if item.get("relative_path") else ""
            dest_fname = item.get("destination_filename") or ""

            target_file_path = ""
            if dest_p and os.path.exists(dest_p):
                target_file_path = dest_p
            elif target_rel_p and os.path.exists(normalize_win_path(os.path.join(self.target_dir, target_rel_p))):
                target_file_path = normalize_win_path(os.path.join(self.target_dir, target_rel_p))
            elif rel_p and os.path.exists(normalize_win_path(os.path.join(self.target_dir, rel_p))):
                target_file_path = normalize_win_path(os.path.join(self.target_dir, rel_p))
            else:
                # Lazy-build disk index only if direct paths failed
                if disk_file_index is None:
                    disk_file_index = {}
                    if os.path.exists(norm_target):
                        for root, _, files in os.walk(norm_target):
                            for f in files:
                                fp = normalize_win_path(os.path.join(root, f))
                                disk_file_index[f.lower()] = fp
                                rel = normalize_win_path(os.path.relpath(fp, norm_target))
                                disk_file_index[rel.lower()] = fp

                if target_rel_p and target_rel_p.lower() in disk_file_index:
                    target_file_path = disk_file_index[target_rel_p.lower()]
                elif rel_p.lower() in disk_file_index:
                    target_file_path = disk_file_index[rel_p.lower()]
                elif dest_fname and dest_fname.lower() in disk_file_index:
                    target_file_path = disk_file_index[dest_fname.lower()]
                elif fname and fname.lower() in disk_file_index:
                    target_file_path = disk_file_index[fname.lower()]

            if target_file_path and os.path.exists(target_file_path):
                pending.append((target_file_path, h_val, fname))

        # Extract in batches rather than spawning ExifTool once per file.
        backfilled_count = register_metadata_batched(self, pending)

        if backfilled_count > 0:
            self.checkpoint()

        return backfilled_count


    def get_generation(self) -> int:
        """Returns the catalog generation counter (0 if never bumped)."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM catalog_meta WHERE key = 'generation'"
            ).fetchone()
            if not row or row["value"] is None:
                return 0
            try:
                return int(row["value"])
            except (TypeError, ValueError):
                return 0

    def bump_generation(self) -> int:
        """Increments the monotonic catalog generation and records last_import time.

        Consumers that attach the catalog read-only/immutable poll this value to decide
        when to re-open and re-scan. Pair with finalize() at session end so the bumped
        value is checkpointed together with the rows it accounts for.
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO catalog_meta (key, value) VALUES ('generation', '1')
                ON CONFLICT(key) DO UPDATE SET
                    value = CAST(CAST(catalog_meta.value AS INTEGER) + 1 AS TEXT)
                """
            )
            conn.execute(
                """
                INSERT INTO catalog_meta (key, value) VALUES ('last_import', CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = CURRENT_TIMESTAMP
                """
            )
            row = conn.execute(
                "SELECT value FROM catalog_meta WHERE key = 'generation'"
            ).fetchone()
            return int(row["value"])

    def set_in_progress(self, in_progress: bool = True):
        """Sets the 'in_progress' flag in catalog_meta so readers can guard against mid-write state."""
        val = "1" if in_progress else "0"
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO catalog_meta (key, value) VALUES ('in_progress', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (val,))

    def is_in_progress(self) -> bool:
        """Returns True if catalog has in_progress == '1'."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM catalog_meta WHERE key = 'in_progress'").fetchone()
            return bool(row and row["value"] == "1")

    def checkpoint(self):
        """Runs a WAL checkpoint to flush WAL logs to disk."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    def finalize(self):
        """Leave the catalog quiescent for external readers at end of session.

        QuickImageCullLAN attaches this database with ?mode=ro&immutable=1, which makes
        SQLite ignore the -wal/-shm sidecars entirely and skip change detection. If a
        committed transaction still lives only in the WAL, that reader silently misses
        it; if it opens mid-write, it can read a torn page. So on session end we flush
        the WAL into the main file (TRUNCATE checkpoint) and switch the journal back to
        DELETE mode, which removes the -wal/-shm sidecars once the connection closes.
        The next write re-enters WAL automatically via _get_connection().
        """
        # Clear in_progress flag before checkpointing so external readers see clean state
        try:
            self.set_in_progress(False)
        except Exception:
            pass

        # Phase 1: flush every committed frame from the WAL into the main db file.
        # After a TRUNCATE checkpoint the -wal is emptied, so an immutable reader already
        # sees all committed data safely even if the sidecar files still exist.
        conn = self._get_connection()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.commit()
        finally:
            conn.close()

        # Other methods open connections via `with self._get_connection()`, which commits
        # but does not close; those lingering handles hold the shared WAL lock and would
        # block the DELETE-mode conversion below. Collect them first.
        gc.collect()

        # Phase 2: convert out of WAL so the -wal/-shm sidecars are removed on close.
        # Best-effort: if a reader still holds the file, the already-emptied WAL is safe.
        try:
            conn = self._get_connection()
            try:
                conn.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
            finally:
                conn.close()
        except sqlite3.OperationalError as exc:
            logging.warning(
                f"finalize: WAL flushed but could not drop sidecars (still locked): {exc}"
            )



