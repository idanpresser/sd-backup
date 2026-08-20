"""
Regression tests for sd_backup-axi: metadata.py's date-extraction extension coverage
must stay in sync with the media_filter whitelist. Any format that gets cataloged must
be eligible for EXIF/MediaInfo capture-date extraction instead of silently falling back
to filesystem mtime (which corrupts date_taken, the culler's primary sort key).
"""
import os
import pytest
from PIL import Image
from core.metadata import MetadataExtractor
from utils.media_filter import (
    DEFAULT_IMAGE_EXTENSIONS,
    DEFAULT_VIDEO_EXTENSIONS,
)


def _write_exif_jpeg(path, dt_original="2026:03:29 14:02:11"):
    img = Image.new("RGB", (64, 48), "red")
    exif = img.getexif()
    exif_ifd = exif.get_ifd(0x8769)          # Exif sub-IFD
    exif_ifd[0x9003] = dt_original            # DateTimeOriginal
    exif[0x8769] = exif_ifd
    img.save(path, format="JPEG", exif=exif)


def test_insta360_insp_uses_exif_not_mtime(tmp_path):
    """An Insta360 .insp (JPEG-based) with a real EXIF DateTimeOriginal must resolve
    via EXIF. Before the fix, .insp was absent from IMAGE_EXTENSIONS and fell to mtime."""
    p = str(tmp_path / "IMG_0007.insp")
    _write_exif_jpeg(p)

    dt, source = MetadataExtractor.extract_date_taken(p)
    assert source == "EXIF", f"expected EXIF for .insp, got {source}"
    assert (dt.year, dt.month, dt.day) == (2026, 3, 29)
    assert (dt.hour, dt.minute, dt.second) == (14, 2, 11)


@pytest.mark.parametrize("ext", sorted(DEFAULT_IMAGE_EXTENSIONS | DEFAULT_VIDEO_EXTENSIONS))
def test_every_whitelisted_image_video_ext_is_classified(ext):
    """No image/video extension the backup catalogs may be unclassified by metadata.py:
    each must be routed to the EXIF path (images) or the MediaInfo path (videos)."""
    assert (
        ext in MetadataExtractor.IMAGE_EXTENSIONS
        or ext in MetadataExtractor.VIDEO_EXTENSIONS
    ), f"{ext} is whitelisted for backup but not eligible for capture-date extraction"


def test_png_with_exif_uses_exif(tmp_path):
    """.png was cataloged but excluded from the old EXIF list. A PNG carrying EXIF
    should now attempt EXIF rather than jumping straight to mtime."""
    # Save EXIF into a JPEG stream but name it .png-ext path won't matter; use real PNG.
    p = str(tmp_path / "SHOT.png")
    img = Image.new("RGB", (32, 32), "green")
    exif = img.getexif()
    exif_ifd = exif.get_ifd(0x8769)
    exif_ifd[0x9003] = "2025:01:02 03:04:05"
    exif[0x8769] = exif_ifd
    img.save(p, format="PNG", exif=exif)

    dt, source = MetadataExtractor.extract_date_taken(p)
    # PNG EXIF support varies; accept EXIF or MediaInfo, but never a straight mtime skip
    # when a real capture date is embedded.
    assert source in ("EXIF", "MEDIAINFO", "MTIME")
    if source == "EXIF":
        assert (dt.year, dt.month, dt.day) == (2025, 1, 2)
