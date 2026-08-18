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

# Shooting modes & special tag keywords to preserve in uppercase
SPECIAL_TAGS = {
    "PANO", "PANORAMA", "BURST", "HDR", "STACK", "TIMELAPSE", 
    "HYPERLAPSE", "PORTRAIT", "NIGHT", "SLOWMO", "SLOW_MO", 
    "STEREO", "3D", "RAW", "EDITED", "COLLAGE", "PRO", "TRASH", "CLIP"
}

# Drone / Action sub-channel single letter flags (e.g., DJI D-Log, Wide, Zoom, Thermal)
DRONE_FLAGS = {"D", "T", "W", "Z", "S"}

# Generic camera & device prefixes to strip
GENERIC_PREFIX_REGEX = re.compile(
    r'^(?:_MG_|__MG_|IMG_|__IMG_|^IMG|^_IMG|DSC_|__DSC_|_DSC|^DSC|DJI_|DJI|PXL_|VID_|VIDEO_|MVIMG_|GOPR|GX\d{2}|GH\d{2}|SAM_|PHOTO_|PIC_|PICTURE_|IMAGE_|WP_|SCREENSHOT_|SCREEN_)[_\-.]*',
    re.IGNORECASE
)


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
    Extracts clip sequence numbers, strips generic camera/brand prefixes (IMG_, DJI_, DSC, etc.) 
    and redundant embedded timestamps from filename stem, while preserving custom names and 
    special shooting tags (PANO, BURST, HDR, D, TIMELAPSE, etc.).

    Examples:
      'DJI_20260811150626_0113_D.MP4' -> ('0113_D', '0113')
      'IMG_20260811_150626_0452.JPG'  -> ('0452', '0452')
      'DSC00123.JPG'                 -> ('00123', '00123')
      'IMG_0001.JPG'                 -> ('0001', '0001')
      'PXL_20260811_150626123.PANO.jpg' -> ('PANO', '')
      'IMG_20260811_150626.JPG'      -> ('', '')
    """
    stem = os.path.splitext(os.path.basename(original_filename))[0]

    # 1. Detect and strip embedded timestamp patterns
    timestamp_patterns = [
        r'(?:19|20)\d{15}',                   # 17-digit timestamp e.g. 20260811150626123
        r'(?:19|20)\d{12}',                   # 14-digit YYYYMMDDHHMMSS e.g. 20260811150626
        r'(?:19|20)\d{6}[_\-.]\d{6}(?:\d{3})?', # YYYYMMDD_HHMMSS or YYYYMMDD_HHMMSS123
        r'(?:19|20)\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}[_\-]\d{2}',  # YYYY-MM-DD-HH-MM-SS
        r'(?:19|20)\d{6}'                     # 8-digit date YYYYMMDD
    ]

    cleaned_stem = stem
    for pattern in timestamp_patterns:
        cleaned_stem = re.sub(pattern, '', cleaned_stem)

    # 2. Strip generic camera/device prefixes
    cleaned_stem = GENERIC_PREFIX_REGEX.sub('', cleaned_stem)

    # Clean up residual multiple underscores, dots, or hyphens
    cleaned_stem = re.sub(r'[_\-.]{2,}', '_', cleaned_stem).replace('.', '_').strip('_- ')

    # Canonicalize uppercase for special mode tags and drone flags
    if cleaned_stem:
        tokens = cleaned_stem.split('_')
        canon_tokens = []
        for tok in tokens:
            tok_upper = tok.upper()
            if tok_upper in SPECIAL_TAGS or tok_upper in DRONE_FLAGS:
                canon_tokens.append(tok_upper)
            else:
                canon_tokens.append(tok)
        cleaned_stem = "_".join(canon_tokens)

    # 3. Extract sequence number (e.g. 0113 or 0452 or 00123)
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
    Formats target filename: YYYYMMDD_HHMMSS[_<CleanStem>][_<Suffix>].<ext>
    Strips redundant embedded timestamps and generic camera/device prefixes.
    Places custom suffix always at the end of the filename stem right before the file extension.
    """
    timestamp = dt.strftime("%Y%m%d_%H%M%S")
    _, ext = os.path.splitext(original_filename)
    if not ext:
        ext = ""

    cleaned_stem, extracted_seq = extract_sequence_and_clean_stem(original_filename)
    sanitized_suffix = sanitize_path(suffix) if suffix else ""

    parts = [timestamp]
    if cleaned_stem:
        parts.append(cleaned_stem)

    if sanitized_suffix:
        if not (cleaned_stem and (cleaned_stem.endswith(f"_{sanitized_suffix}") or cleaned_stem == sanitized_suffix)):
            parts.append(sanitized_suffix)

    full_stem = "_".join(parts)
    full_stem = re.sub(r'[_\-]{2,}', '_', full_stem).strip('_-')
    return f"{full_stem}{ext}"


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
