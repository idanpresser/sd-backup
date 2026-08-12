"""
Path formatting utilities for SD-FastBackup.
Organizes destination directories, preserves panorama/burst/stack subfolders, 
provides smart filename sequence extraction, and applies multi-layer media filtering.
"""
import os
import re
import sys
from datetime import datetime
from typing import List, Optional, Tuple
from utils.media_filter import is_media_file


# Stack/special folder keywords to preserve in target structure
STACK_KEYWORDS = {"PANO", "PANORAMA", "BURST", "HDR", "STACK", "TIMELAPSE", "STEREO", "3D", "TRASH", "CLIP"}


def normalize_win_path(path_str: str) -> str:
    """Normalizes slashes to Windows backslashes '\\' on Windows systems."""
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


def extract_sequence_and_clean_stem(original_filename: str) -> Tuple[str, str]:
    """
    Extracts clip sequence numbers and removes redundant embedded timestamps from filename stem.
    Example:
      'DJI_20260811150626_0113_D.MP4' -> ('DJI_0113_D', '0113')
      'IMG_20260811_150626_0452.JPG'  -> ('IMG_0452', '0452')
      'DSC00123.JPG'                 -> ('DSC00123', '00123')
    """
    stem = os.path.splitext(os.path.basename(original_filename))[0]

    # 1. Detect and strip embedded timestamp patterns
    timestamp_patterns = [
        r'(?:19|20)\d{12}',                   # 14-digit YYYYMMDDHHMMSS e.g. 20260811150626
        r'(?:19|20)\d{6}[_\-]\d{6}',          # YYYYMMDD_HHMMSS e.g. 20260811_150626
        r'(?:19|20)\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}',  # YYYY-MM-DD-HH-MM-SS
        r'(?:19|20)\d{6}'                     # 8-digit date YYYYMMDD
    ]

    cleaned_stem = stem
    for pattern in timestamp_patterns:
        cleaned_stem = re.sub(pattern, '', cleaned_stem)

    # Clean up residual multiple underscores or hyphens
    cleaned_stem = re.sub(r'[_\-]{2,}', '_', cleaned_stem).strip('_-')

    if not cleaned_stem:
        cleaned_stem = stem

    # 2. Extract sequence number (e.g. 0113 or 0452 or 00123)
    num_matches = re.findall(r'\d+', cleaned_stem)
    extracted_seq = num_matches[-1] if num_matches else ""

    return cleaned_stem, extracted_seq


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
    Formats target filename: YYYYMMDD_HHMMSS_<Suffix_Or_CleanStem>.<ext>
    Strips redundant embedded timestamps from original filename.
    """
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ""

    cleaned_stem, extracted_seq = extract_sequence_and_clean_stem(original_filename)
    sanitized_suffix = sanitize_path(suffix) if suffix else ""

    if sanitized_suffix:
        brand_prefixes = [r'^DJI_', r'^IMG_', r'^DSC_', r'^GX\d{2}']
        stem_no_brand = cleaned_stem
        for bp in brand_prefixes:
            stem_no_brand = re.sub(bp, '', stem_no_brand)
        
        if stem_no_brand and stem_no_brand != cleaned_stem:
            middle = f"{sanitized_suffix}_{stem_no_brand}"
        else:
            middle = f"{sanitized_suffix}_{cleaned_stem}"
    else:
        middle = cleaned_stem

    middle = re.sub(r'[_\-]{2,}', '_', middle).strip('_-')
    return f"{timestamp}_{middle}{ext}"


def extract_stack_subfolder(original_rel_path: str) -> Optional[str]:
    """
    Checks if original relative path contains a panorama/burst/stack subfolder name and returns it.
    """
    if not original_rel_path:
        return None

    parts = normalize_win_path(original_rel_path).split(os.sep)
    for part in parts[:-1]:
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
    Filters out non-media system files automatically using multi-layer media filter.
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
                    if is_media_file(full_f):
                        collected_files.append(full_f)

    return collected_files
