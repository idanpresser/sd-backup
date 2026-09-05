"""
Multi-Layer Media File Filter and Configurable Extension Manager for SD-FastBackup.
Prevents non-media files (Lightroom catalogs, database caches, files without extensions, system files)
from being scanned, transferred, or cataloged, while allowing user-defined media extension customization.
"""
import os
import logging
from typing import Set, Iterable, Optional, Dict, List

# Layer 1: Blacklisted system filenames and keywords (instant drop)
SYSTEM_BLACKLIST_FILENAMES = {
    "indexervolumeguid", "wpsettings", "sonycard.ind", "desktop.ini",
    "thumbs.db", ".ds_store", "pp-101.db", "index.bdm", "movieobj.bdm",
    "prv00001.bin", "avin0001.bnp", "avin0001.inp", "avin0001.int"
}

# Layer 1: Blacklisted non-media file extensions (instant drop)
SYSTEM_BLACKLIST_EXTENSIONS = {
    # System & Database
    ".db", ".dat", ".ind", ".bnp", ".cpi", ".bdm", ".mpl", ".bin",
    ".inp", ".int", ".sys", ".ini", ".tmp", ".log", ".bak", ".exe", ".dll",
    
    # Adobe & Lightroom Catalog / Cache Files
    ".lrcat", ".lrdata", ".lrcat-data", ".lrcat-lock", ".lrcat-journal",
    ".bridgecache", ".bridgelevels", ".bct",
    
    # Documents, Office, Archives & Code
    ".txt", ".csv", ".json", ".xml", ".html", ".htm", ".pdf", ".doc", ".docx",
    ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".py", ".js", ".css", ".cpp", ".c", ".h", ".cs", ".java"
}

# Default Media Extension Categories
DEFAULT_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp", ".bmp", ".gif",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".orf", ".rw2", ".pef",
    ".raf", ".srw", ".erf", ".3fr", ".iiq", ".nrw", ".kdc", ".dcr", ".mos", ".mef",
    ".insp"
}

DEFAULT_VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpg", ".mpeg",
    ".m2ts", ".mts", ".ts", ".3gp", ".flv", ".wmv", ".vob",
    ".insv", ".braw", ".r3d", ".crm"
}

DEFAULT_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".wma", ".opus", ".alac"
}

DEFAULT_SIDECAR_EXTENSIONS = {
    ".thm", ".lrf", ".xmp", ".scr"
}

DEFAULT_MEDIA_EXTENSIONS: Set[str] = (
    DEFAULT_IMAGE_EXTENSIONS | 
    DEFAULT_VIDEO_EXTENSIONS | 
    DEFAULT_AUDIO_EXTENSIONS | 
    DEFAULT_SIDECAR_EXTENSIONS
)

# Active Media Extensions (Runtime Mutable State)
_ACTIVE_MEDIA_EXTENSIONS: Set[str] = set(DEFAULT_MEDIA_EXTENSIONS)

# Backward Compatibility Alias
MEDIA_WHITELIST_EXTENSIONS: Set[str] = _ACTIVE_MEDIA_EXTENSIONS


def normalize_extension(ext: str) -> str:
    """Normalizes an extension string to lower-case with leading dot (e.g. 'JPG' -> '.jpg')."""
    if not ext:
        return ""
    clean = ext.strip().lower()
    if not clean.startswith('.'):
        clean = f".{clean}"
    return clean


def get_active_media_extensions() -> Set[str]:
    """Returns the current set of active whitelisted media extensions."""
    return set(_ACTIVE_MEDIA_EXTENSIONS)


def set_active_media_extensions(exts: Iterable[str]):
    """Sets the active media extensions from an iterable."""
    global _ACTIVE_MEDIA_EXTENSIONS, MEDIA_WHITELIST_EXTENSIONS
    normalized = {normalize_extension(e) for e in exts if normalize_extension(e)}
    _ACTIVE_MEDIA_EXTENSIONS.clear()
    _ACTIVE_MEDIA_EXTENSIONS.update(normalized)
    MEDIA_WHITELIST_EXTENSIONS = _ACTIVE_MEDIA_EXTENSIONS


def add_media_extension(ext: str) -> bool:
    """Adds a custom extension to the active whitelist. Returns True if added."""
    norm = normalize_extension(ext)
    if not norm or norm == '.':
        return False
    _ACTIVE_MEDIA_EXTENSIONS.add(norm)
    return True


def remove_media_extension(ext: str) -> bool:
    """Removes an extension from the active whitelist. Returns True if removed."""
    norm = normalize_extension(ext)
    if norm in _ACTIVE_MEDIA_EXTENSIONS:
        _ACTIVE_MEDIA_EXTENSIONS.remove(norm)
        return True
    return False


def reset_default_media_extensions():
    """Resets active media extensions to default built-in formats."""
    global _ACTIVE_MEDIA_EXTENSIONS, MEDIA_WHITELIST_EXTENSIONS
    _ACTIVE_MEDIA_EXTENSIONS.clear()
    _ACTIVE_MEDIA_EXTENSIONS.update(DEFAULT_MEDIA_EXTENSIONS)
    MEDIA_WHITELIST_EXTENSIONS = _ACTIVE_MEDIA_EXTENSIONS


def is_blacklisted_system_file(file_path: str) -> bool:
    """Returns True if file is a known non-media system/database file or Lightroom catalog."""
    if not file_path:
        return True

    base = os.path.basename(file_path).lower().strip()
    if not base or base.startswith('.'):
        return True

    for keyword in SYSTEM_BLACKLIST_FILENAMES:
        if keyword in base:
            return True

    ext = os.path.splitext(base)[1].lower()
    if ext in SYSTEM_BLACKLIST_EXTENSIONS:
        return True

    return False


def is_media_file(file_path: str, custom_extensions: Optional[Set[str]] = None) -> bool:
    """
    Strictly evaluates whether a file is a valid media file or camera sidecar.
    Rules:
    1. Rejects empty paths or hidden/system files starting with '.'
    2. Rejects files with no extension (e.g. 'DSC00123' or 'file')
    3. Rejects blacklisted filenames and extensions (e.g. Lightroom catalogs, system DBs)
    4. Accepts files whose extension matches active/custom media whitelist.
    5. Fallback inspection via MediaInfo only for real audio/video/image streams (never mtime).
    """
    if not file_path:
        return False

    base = os.path.basename(file_path).strip()
    if not base or base.startswith('.'):
        return False

    # Layer 1: Blacklist check
    if is_blacklisted_system_file(file_path):
        return False

    _, ext = os.path.splitext(base)
    ext = ext.lower().strip()

    # Rule: Must have a non-empty extension
    if not ext or ext == '.':
        return False

    active_exts = custom_extensions if custom_extensions is not None else _ACTIVE_MEDIA_EXTENSIONS
    if ext in active_exts:
        return True

    # Layer 3: True Container Inspection (Only if file exists on disk and has valid media streams)
    if os.path.exists(file_path):
        try:
            from pymediainfo import MediaInfo
            info = MediaInfo.parse(file_path)
            has_media_track = any(t.track_type in {'Image', 'Video', 'Audio'} for t in info.tracks)
            if has_media_track:
                return True
        except Exception:
            pass

    return False
