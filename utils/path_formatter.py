"""
Path formatting utilities for SD-FastBackup.
Organizes destination directories and renames files based on date_taken.
"""
import os
import re
from datetime import datetime
from typing import List


def sanitize_path(path_str: str) -> str:
    """Removes or replaces invalid filesystem characters from filename or path component."""
    # Replace characters illegal in Windows paths: < > : " | ? *
    sanitized = re.sub(r'[<>:"|?*]', '_', path_str)
    return sanitized.strip()


def format_target_relative_dir(dt: datetime) -> str:
    """
    Formats directory structure relative to target root: YYYY/YYYY-MM/YYYY-MM-DD
    """
    year = dt.strftime("%Y")
    year_month = dt.strftime("%Y-%m")
    year_month_day = dt.strftime("%Y-%m-%d")
    return os.path.join(year, year_month, year_month_day)


def format_target_filename(dt: datetime, original_filename: str, suffix: str = "") -> str:
    """
    Formats target filename: YYYYMMDD_HHMMSS_<Suffix_Or_OriginalName>.<ext>
    If suffix is provided, uses suffix in place of original stem or appended to timestamp.
    """
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ""
    
    stem = os.path.splitext(original_filename)[0]
    middle = sanitize_path(suffix) if suffix else sanitize_path(stem)
    
    return f"{timestamp}_{middle}{ext}"


def format_full_target_path(target_root: str, dt: datetime, original_filename: str, suffix: str = "") -> str:
    """
    Returns full destination target path for a file.
    """
    rel_dir = format_target_relative_dir(dt)
    filename = format_target_filename(dt, original_filename, suffix=suffix)
    return os.path.join(target_root, rel_dir, filename)


def filter_source_files(source_root: str, include_dcim: bool = True, include_private: bool = True, full_volume: bool = False) -> List[str]:
    """
    Discovers source files within specified directories (DCIM, PRIVATE, or full volume).
    """
    if not os.path.exists(source_root):
        return []

    collected_files = []
    
    if full_volume:
        target_paths = [source_root]
    else:
        target_paths = []
        if include_dcim:
            dcim_dir = os.path.join(source_root, "DCIM")
            if os.path.exists(dcim_dir):
                target_paths.append(dcim_dir)
        if include_private:
            private_dir = os.path.join(source_root, "PRIVATE")
            if os.path.exists(private_dir):
                target_paths.append(private_dir)
        if not target_paths:
            # Fallback to root if neither DCIM nor PRIVATE exists
            target_paths.append(source_root)

    for search_dir in target_paths:
        for root, _, files in os.walk(search_dir):
            for f in files:
                if not f.startswith('.'):
                    collected_files.append(os.path.join(root, f))

    return collected_files
