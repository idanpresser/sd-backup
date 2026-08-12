"""
Metadata Engine & Composite Hasher for SD-FastBackup.
Extracts Date Taken via EXIF (including RAW formats), PyMediaInfo, or mtime fallback, and computes fast composite SHA256 hashes.
"""
import os
import hashlib
from datetime import datetime
from typing import Tuple
import exifread
from pymediainfo import MediaInfo


class MetadataExtractor:
    """Extracts Date Taken and Size to generate a unique composite hash."""

    IMAGE_EXTENSIONS = (
        '.jpg', '.jpeg', '.tif', '.tiff', '.heic',
        '.nef', '.cr2', '.cr3', '.arw', '.dng', '.raw', 
        '.orf', '.rw2', '.pef', '.raf', '.srw', '.erf', '.3fr', '.iiq', '.nrw'
    )
    VIDEO_EXTENSIONS = (
        '.mp4', '.mov', '.mxf', '.crm', '.ari', '.avi', '.mkv', '.braw', '.mts', '.m2ts'
    )

    @staticmethod
    def get_file_size(file_path: str) -> int:
        """Returns file size in bytes."""
        return os.path.getsize(file_path)

    @classmethod
    def extract_date_taken(cls, file_path: str) -> Tuple[datetime, str]:
        """
        Attempts date_taken extraction via:
        1. EXIF Metadata (exifread for photo and camera RAW files)
        2. MediaInfo Container Metadata (pymediainfo for video files)
        3. Fallback to Filesystem mtime
        Returns: (datetime_object, source_name_str)
        """
        ext = os.path.splitext(file_path)[1].lower()

        # 1. EXIF Extraction for Images & RAWs
        if ext in cls.IMAGE_EXTENSIONS:
            try:
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f, stop_tag='EXIF DateTimeOriginal', details=False)
                    if 'EXIF DateTimeOriginal' in tags:
                        date_str = str(tags['EXIF DateTimeOriginal']).strip()
                        # Format usually: YYYY:MM:DD HH:MM:SS
                        dt = datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
                        return dt, "EXIF"
            except Exception:
                pass

        # 2. PyMediaInfo Extraction for Videos
        if ext in cls.VIDEO_EXTENSIONS:
            try:
                media_info = MediaInfo.parse(file_path)
                for track in media_info.tracks:
                    if track.track_type == 'General':
                        date_candidates = [
                            getattr(track, 'encoded_date', None),
                            getattr(track, 'tagged_date', None),
                            getattr(track, 'file_last_modification_date', None)
                        ]
                        for candidate in date_candidates:
                            if candidate:
                                clean_str = str(candidate).replace("UTC ", "").strip()
                                try:
                                    dt = datetime.strptime(clean_str[:19], '%Y-%m-%d %H:%M:%S')
                                    return dt, "MEDIAINFO"
                                except Exception:
                                    pass
            except Exception:
                pass

        # 3. Fallback: Filesystem Modification Time (mtime)
        try:
            mtime = os.path.getmtime(file_path)
            dt = datetime.fromtimestamp(mtime)
            dt = dt.replace(microsecond=0)
            return dt, "MTIME"
        except Exception:
            now = datetime.now().replace(microsecond=0)
            return now, "FALLBACK"

    @classmethod
    def compute_hash_from_values(cls, date_taken: datetime, size_bytes: int) -> str:
        """
        Generates SHA256 composite hash string directly from date_taken datetime and size_bytes.
        Used for virtual MTP files where date and size are already extracted.
        """
        iso_date = date_taken.strftime("%Y-%m-%dT%H:%M:%S")
        raw_key = f"{iso_date}_{size_bytes}"
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    @classmethod
    def compute_composite_hash(cls, file_path: str) -> Tuple[str, int, datetime, str]:
        """
        Generates SHA256 composite hash string from: f"{date_taken_iso}_{file_size_bytes}"
        Returns: (composite_hash_hex, size_bytes, date_taken_dt, source_type)
        """
        size = cls.get_file_size(file_path)
        date_taken, source = cls.extract_date_taken(file_path)

        composite_hash = cls.compute_hash_from_values(date_taken, size)
        return composite_hash, size, date_taken, source
