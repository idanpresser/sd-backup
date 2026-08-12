"""
Path formatting utilities for SD-FastBackup.
Organizes destination directories, preserves panorama/burst/stack subfolders, and resolves filename collisions.
"""
import os
import re
import sys
from datetime import datetime
from typing import List, Optional


# Stack/special folder keywords to preserve in target structure
STACK_KEYWORDS = {"PANO", "PANORAMA", "BURST", "HDR", "STACK", "TIMELAPSE", "STEREO", "3D", "TRASH", "CLIP"}


def normalize_win_path(path_str: str) -> str:
    """Normalizes slashes to Windows backslashes '\\' on Windows systems, removing trailing backslashes for CLI arguments."""
    if not path_str:
        return ""
    norm = os.path.normpath(path_str)
    if sys.platform == "win32" or os.name == "nt":
        norm = norm.replace("/", "\\")
    return norm


def sanitize_path(path_str: str) -> str:
    """Removes or replaces invalid filesystem characters from filename or path component."""
    sanitized = re.sub(r'[<>:"|?*]', '_', path_str)
    return sanitized.strip()


def format_target_relative_dir(dt: datetime) -> str:
    """
    Formats directory structure relative to target root: YYYY/YYYY-MM/YYYY-MM-DD
    """
    year = dt.strftime("%Y")
    year_month = dt.strftime("%Y-%m")
    year_month_day = dt.strftime("%Y-%m-%d")
    return normalize_win_path(os.path.join(year, year_month, year_month_day))


def format_target_filename(dt: datetime, original_filename: str, suffix: str = "") -> str:
    """
    Formats target filename: YYYYMMDD_HHMMSS_<Suffix_Or_OriginalName>.<ext>
    """
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ""
    
    stem = os.path.splitext(original_filename)[0]
    middle = sanitize_path(suffix) if suffix else sanitize_path(stem)
    
    return f"{timestamp}_{middle}{ext}"


def extract_stack_subfolder(original_rel_path: str) -> Optional[str]:
    """
    Checks if original relative path contains a panorama/burst/stack subfolder name and returns it.
    Example: 'DCIM/100EOS/PANO/IMG_0001.JPG' -> 'PANO'
    """
    if not original_rel_path:
        return None

    parts = normalize_win_path(original_rel_path).split(os.sep)
    for part in parts[:-1]:  # Exclude file name
        part_upper = part.upper()
        if part_upper in STACK_KEYWORDS or any(kw in part_upper for kw in STACK_KEYWORDS):
            return sanitize_path(part)

    return None


def format_full_target_path(
    target_root: str, 
    dt: datetime, 
    original_filename: str, 
    suffix: str = "", 
    original_rel_path: str = ""
) -> str:
    """
    Returns full destination target path for a file, preserving stack folders if present.
    Format: <Target_Root>\\YYYY\\YYYY-MM\\YYYY-MM-DD\\[Stack_Folder\\]YYYYMMDD_HHMMSS_<Suffix>.<ext>
    """
    rel_dir = format_target_relative_dir(dt)
    filename = format_target_filename(dt, original_filename, suffix=suffix)

    stack_dir = extract_stack_subfolder(original_rel_path) if original_rel_path else None
    
    if stack_dir:
        full_p = os.path.join(target_root, rel_dir, stack_dir, filename)
    else:
        full_p = os.path.join(target_root, rel_dir, filename)

    return normalize_win_path(full_p)


def resolve_target_path_collision(target_path: str) -> str:
    """
    If target_path already exists on disk, appends _1, _2, _3 counter to filename to avoid overwriting.
    """
    if not os.path.exists(target_path):
        return normalize_win_path(target_path)

    parent_dir = os.path.dirname(target_path)
    filename = os.path.basename(target_path)
    stem, ext = os.path.splitext(filename)

    counter = 1
    new_target = os.path.join(parent_dir, f"{stem}_{counter}{ext}")
    while os.path.exists(new_target):
        counter += 1
        new_target = os.path.join(parent_dir, f"{stem}_{counter}{ext}")

    return normalize_win_path(new_target)


def filter_source_files(
    source_root: str, 
    include_dcim: bool = True, 
    include_private: bool = True, 
    full_volume: bool = False
) -> List[str]:
    """
    Discovers source files within specified directories (DCIM, PRIVATE, or full volume / custom folder).
    Always returns normalized paths.
    """
    norm_source = normalize_win_path(source_root)
    if not os.path.exists(norm_source):
        return []

    collected_files = []
    
    has_dcim = os.path.exists(os.path.join(norm_source, "DCIM"))
    has_private = os.path.exists(os.path.join(norm_source, "PRIVATE"))

    if full_volume or (not has_dcim and not has_private):
        target_paths = [norm_source]
    else:
        target_paths = []
        if include_dcim and has_dcim:
            target_paths.append(os.path.join(norm_source, "DCIM"))
        if include_private and has_private:
            target_paths.append(os.path.join(norm_source, "PRIVATE"))
        if not target_paths:
            target_paths.append(norm_source)

    for search_dir in target_paths:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if not f.startswith('.'):
                    full_f = normalize_win_path(os.path.join(root, f))
                    collected_files.append(full_f)

    return collected_files
