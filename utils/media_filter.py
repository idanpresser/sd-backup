"""
Multi-Layer Media File Filter for SD-FastBackup.
Layer 1: Blacklist System & Database Index Files (Instant Drop)
Layer 2: Whitelist Media & Camera Sidecar Extensions (Instant Accept)
Layer 3: PyMediaInfo / EXIF Fallback Inspection (For Unknown Extensions)
"""
import os
import logging
from typing import Optional

# Layer 1: Blacklisted filenames and keywords (instant drop)
SYSTEM_BLACKLIST_FILENAMES = {
    "indexervolumeguid", "wpsettings", "sonycard.ind", "desktop.ini",
    "thumbs.db", ".ds_store", "pp-101.db", "index.bdm", "movieobj.bdm",
    "prv00001.bin", "avin0001.bnp", "avin0001.inp", "avin0001.int"
}

SYSTEM_BLACKLIST_EXTENSIONS = {
    ".db", ".dat", ".ind", ".bnp", ".cpi", ".bdm", ".mpl", ".bin",
    ".inp", ".int", ".sys", ".ini", ".tmp", ".log", ".bak", ".exe", ".dll"
}

# Layer 2: Whitelisted Media & Camera Sidecar extensions (instant accept)
MEDIA_WHITELIST_EXTENSIONS = {
    # Image & RAW Formats
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".bmp",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".orf", ".rw2", ".pef",
    ".raf", ".srw", ".erf", ".3fr", ".iiq", ".nrw",

    # Video Formats
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpg", ".mpeg",
    ".m2ts", ".mts", ".ts", ".3gp", ".flv", ".wmv", ".vob",

    # Audio Formats
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".wma",

    # Camera Sidecars & Previews (GoPro, DJI, Sony, Canon)
    ".thm", ".lrf", ".xmp", ".scr"
}


def is_blacklisted_system_file(file_path: str) -> bool:
    """Returns True if file is a known non-media system/database file."""
    if not file_path:
        return True

    base = os.path.basename(file_path).lower()
    for keyword in SYSTEM_BLACKLIST_FILENAMES:
        if keyword in base:
            return True

    ext = os.path.splitext(base)[1]
    if ext in SYSTEM_BLACKLIST_EXTENSIONS:
        return True

    return False


def is_media_file(file_path: str) -> bool:
    """
    Evaluates whether a file is a media file (or camera sidecar) using 3 layers:
    1. Blacklist check (Instant Drop)
    2. Whitelist extension check (Instant Accept)
    3. PyMediaInfo / EXIF fallback inspection
    """
    if not file_path:
        return False

    # Layer 1: System File Blacklist Check
    if is_blacklisted_system_file(file_path):
        return False

    base = os.path.basename(file_path).lower()
    ext = os.path.splitext(base)[1]

    # Layer 2: Media & Sidecar Whitelist Check
    if ext in MEDIA_WHITELIST_EXTENSIONS:
        return True

    # Layer 3: PyMediaInfo / EXIF Fallback Inspection
    if os.path.exists(file_path):
        try:
            from core.metadata import MetadataExtractor
            dt, _ = MetadataExtractor.extract_date_taken(file_path)
            return dt is not None
        except Exception as e:
            logging.debug(f"MediaInfo inspection notice for '{file_path}': {e}")

    return False
