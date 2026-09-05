"""
Metadata Engine & Composite Hasher for SD-FastBackup.
Extracts Date Taken via EXIF (including RAW formats), PyMediaInfo, or mtime fallback, and computes fast composite SHA256 hashes.
"""
import os
import json
import shutil
import logging
import hashlib
import subprocess
import tempfile
from functools import lru_cache
from datetime import datetime
from typing import Tuple, Dict, Any, Optional, List, Iterable
import exifread
from pymediainfo import MediaInfo
from utils.media_filter import (
    DEFAULT_IMAGE_EXTENSIONS,
    DEFAULT_VIDEO_EXTENSIONS,
    DEFAULT_AUDIO_EXTENSIONS,
)


def _parse_exif_ratio(val) -> float:
    if hasattr(val, 'num') and hasattr(val, 'den') and val.den != 0:
        return float(val.num) / float(val.den)
    try:
        s = str(val).strip()
        if '/' in s:
            n, d = s.split('/')
            return float(n) / float(d) if float(d) != 0 else 0.0
        return float(s)
    except Exception:
        return 0.0


def _parse_gps_coords(tags: dict) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    try:
        lat, lon, alt = None, None, None
        if 'GPS GPSLatitude' in tags and 'GPS GPSLatitudeRef' in tags:
            lat_vals = tags['GPS GPSLatitude'].values
            lat_ref = str(tags['GPS GPSLatitudeRef']).strip().upper()
            lat = _parse_exif_ratio(lat_vals[0]) + _parse_exif_ratio(lat_vals[1])/60.0 + _parse_exif_ratio(lat_vals[2])/3600.0
            if lat_ref == 'S':
                lat = -lat

        if 'GPS GPSLongitude' in tags and 'GPS GPSLongitudeRef' in tags:
            lon_vals = tags['GPS GPSLongitude'].values
            lon_ref = str(tags['GPS GPSLongitudeRef']).strip().upper()
            lon = _parse_exif_ratio(lon_vals[0]) + _parse_exif_ratio(lon_vals[1])/60.0 + _parse_exif_ratio(lon_vals[2])/3600.0
            if lon_ref == 'W':
                lon = -lon

        if 'GPS GPSAltitude' in tags:
            alt_val = tags['GPS GPSAltitude'].values
            val_to_use = alt_val[0] if isinstance(alt_val, list) and alt_val else alt_val
            alt = _parse_exif_ratio(val_to_use)
            if 'GPS GPSAltitudeRef' in tags and str(tags['GPS GPSAltitudeRef']) == '1':
                alt = -alt

        return lat, lon, alt
    except Exception:
        return None, None, None


class MetadataExtractor:
    """Extracts Date Taken, unique composite hashes, and extended EXIF/MediaInfo metadata catalog fields."""

    # Capture-date extraction eligibility is kept in sync with the media_filter
    # whitelist (what actually gets cataloged) so no cataloged format silently skips
    # EXIF/MediaInfo and falls through to mtime. Legacy extras are unioned in so nothing
    # that previously worked regresses. See sd_backup-axi.
    _LEGACY_IMAGE_EXTENSIONS = {
        '.jpg', '.jpeg', '.tif', '.tiff', '.heic',
        '.nef', '.cr2', '.cr3', '.arw', '.dng', '.raw',
        '.orf', '.rw2', '.pef', '.raf', '.srw', '.erf', '.3fr', '.iiq', '.nrw',
    }
    _LEGACY_VIDEO_EXTENSIONS = {
        '.mp4', '.mov', '.mxf', '.crm', '.ari', '.avi', '.mkv', '.braw', '.mts', '.m2ts',
    }
    IMAGE_EXTENSIONS = frozenset(DEFAULT_IMAGE_EXTENSIONS | _LEGACY_IMAGE_EXTENSIONS)
    VIDEO_EXTENSIONS = frozenset(DEFAULT_VIDEO_EXTENSIONS | _LEGACY_VIDEO_EXTENSIONS)
    AUDIO_EXTENSIONS = frozenset(DEFAULT_AUDIO_EXTENSIONS)

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

        # 2. PyMediaInfo Extraction for videos, audio, and any image the EXIF path
        #    could not date (e.g. HEIC/PNG/WebP, which exifread often can't parse).
        if (
            ext in cls.VIDEO_EXTENSIONS
            or ext in cls.AUDIO_EXTENSIONS
            or ext in cls.IMAGE_EXTENSIONS
        ):
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

    @staticmethod
    @lru_cache(maxsize=1)
    def resolve_exiftool_path() -> Optional[str]:
        """Locates exiftool.exe once per process (PATH, then the bundled bin/).

        Resolution used to run inside the per-file extraction call, so a backup of N
        files paid N shutil.which() sweeps on top of N process spawns. The result is
        stable for the life of the process, so it is cached.
        """
        exiftool_path = shutil.which("exiftool") or shutil.which("exiftool.exe")
        if not exiftool_path:
            try:
                from utils.resource_path import get_bin_path
                candidate = get_bin_path("exiftool.exe")
                if os.path.exists(candidate):
                    exiftool_path = candidate
            except Exception:
                pass
        if not exiftool_path:
            bin_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
            candidate = os.path.join(bin_dir, "exiftool.exe")
            if os.path.exists(candidate):
                exiftool_path = candidate
        return exiftool_path

    @classmethod
    def _extract_exiftool_metadata(cls, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Attempts metadata extraction using Phil Harvey's ExifTool CLI utility if available in PATH or bin/.
        """
        exiftool_path = cls.resolve_exiftool_path()
        if not exiftool_path:
            return None

        try:
            cmd = [exiftool_path, "-json", "-G", file_path]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=5)
            data_list = json.loads(res.stdout)
            if not data_list or not isinstance(data_list, list):
                return None

            tags = data_list[0]
            if not isinstance(tags, dict):
                return None

            return cls._map_exiftool_tags(tags)
        except Exception:
            return None

    @classmethod
    def _map_exiftool_tags(cls, tags: Dict[str, Any]) -> Dict[str, Any]:
        """Maps one ExifTool -json -G record onto the file_metadata catalog columns."""
        try:
            meta: Dict[str, Any] = {
                "camera_make": None,
                "camera_model": None,
                "lens_model": None,
                "serial_number": None,
                "iso": None,
                "aperture": None,
                "shutter_speed": None,
                "focal_length": None,
                "white_balance": None,
                "width": None,
                "height": None,
                "aspect_ratio": None,
                "color_space": None,
                "video_codec": None,
                "container_format": None,
                "frame_rate": None,
                "duration_seconds": None,
                "bitrate": None,
                "audio_codec": None,
                "audio_channels": None,
                "audio_sample_rate": None,
                "latitude": None,
                "longitude": None,
                "altitude": None,
                "raw_json": json.dumps(tags, default=str)
            }

            def get_tag(*keys):
                for k in keys:
                    if k in tags:
                        return tags[k]
                    for full_k, v in tags.items():
                        if full_k.endswith(":" + k) or full_k == k:
                            return v
                return None

            meta["camera_make"] = str(get_tag("Make", "EXIF:Make") or "").strip() or None
            meta["camera_model"] = str(get_tag("Model", "EXIF:Model") or "").strip() or None
            meta["lens_model"] = str(get_tag("LensModel", "EXIF:LensModel", "LensInfo") or "").strip() or None
            meta["serial_number"] = str(get_tag("SerialNumber", "BodySerialNumber", "EXIF:SerialNumber") or "").strip() or None

            iso_val = get_tag("ISO", "EXIF:ISO")
            if iso_val:
                try:
                    meta["iso"] = int(str(iso_val).split()[0])
                except Exception:
                    pass

            aperture_val = get_tag("FNumber", "EXIF:FNumber", "ApertureValue")
            if aperture_val:
                try:
                    fnum = float(aperture_val)
                    meta["aperture"] = f"f/{fnum:.1f}" if fnum > 0 else str(aperture_val)
                except Exception:
                    meta["aperture"] = str(aperture_val)

            shutter_val = get_tag("ExposureTime", "EXIF:ExposureTime", "ShutterSpeedValue")
            if shutter_val:
                meta["shutter_speed"] = str(shutter_val).strip()

            focal_val = get_tag("FocalLength", "EXIF:FocalLength")
            if focal_val:
                meta["focal_length"] = str(focal_val).strip()

            wb_val = get_tag("WhiteBalance", "EXIF:WhiteBalance")
            if wb_val:
                meta["white_balance"] = str(wb_val).strip()

            img_size = get_tag("ImageSize", "Composite:ImageSize")
            if img_size and 'x' in str(img_size):
                parts = str(img_size).split('x')
                try:
                    meta["width"] = int(parts[0])
                    meta["height"] = int(parts[1])
                    if meta["width"] and meta["height"] != 0:
                        meta["aspect_ratio"] = f"{meta['width']}:{meta['height']}"
                except Exception:
                    pass

            if not meta["width"]:
                w_val = get_tag("ImageWidth", "EXIF:ExifImageWidth", "File:ImageWidth")
                h_val = get_tag("ImageHeight", "EXIF:ExifImageLength", "File:ImageHeight")
                if w_val and h_val:
                    try:
                        meta["width"] = int(w_val)
                        meta["height"] = int(h_val)
                        if meta["width"] and meta["height"] != 0:
                            meta["aspect_ratio"] = f"{meta['width']}:{meta['height']}"
                    except Exception:
                        pass

            lat_val = get_tag("GPSLatitude", "Composite:GPSLatitude")
            lon_val = get_tag("GPSLongitude", "Composite:GPSLongitude")
            if lat_val and lon_val:
                try:
                    meta["latitude"] = float(lat_val)
                    meta["longitude"] = float(lon_val)
                except Exception:
                    pass

            return meta
        except Exception:
            return None

    @staticmethod
    def _is_usable_exiftool_meta(meta: Optional[Dict[str, Any]]) -> bool:
        """True when an ExifTool record carried enough to skip the library tiers."""
        return bool(meta and (meta.get("camera_make") or meta.get("raw_json") != "{}"))

    @classmethod
    def extract_full_metadata_batch(
        cls,
        file_paths: Iterable[str],
        chunk_size: int = 200,
    ) -> Dict[str, Dict[str, Any]]:
        """Extracts full metadata for many files using one ExifTool process per chunk.

        ExifTool is compiled Perl and pays ~430ms of interpreter startup per invocation,
        so spawning it per file dominated every ingest mode (measured 566ms/file against
        a 0.6ms same-volume rename). Handing it a whole batch amortises that startup to
        ~12ms/file for identical output.

        Paths are passed via a UTF-8 argfile (-@) rather than argv: it sidesteps the
        ~32k Windows command-line limit and carries non-ASCII filenames intact.

        Returns {input_path: metadata_dict} with an entry for every input path; any file
        ExifTool could not describe falls back to the exifread/PyMediaInfo tiers.
        """
        paths = list(file_paths)
        if not paths:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        exiftool_path = cls.resolve_exiftool_path()

        if exiftool_path:
            for start in range(0, len(paths), max(1, chunk_size)):
                chunk = paths[start:start + max(1, chunk_size)]
                for path, tags in cls._run_exiftool_batch(exiftool_path, chunk).items():
                    mapped = cls._map_exiftool_tags(tags)
                    if cls._is_usable_exiftool_meta(mapped):
                        results[path] = mapped

        # Anything ExifTool skipped, could not read, or described uselessly.
        for path in paths:
            if path not in results:
                results[path] = cls._extract_library_metadata(path)

        return results

    @classmethod
    def _run_exiftool_batch(cls, exiftool_path: str, chunk: List[str]) -> Dict[str, Dict[str, Any]]:
        """Runs one ExifTool invocation over a chunk, keyed back to the input paths."""
        argfile = None
        try:
            fd, argfile = tempfile.mkstemp(prefix="sdbackup_exiftool_", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write("-json\n-G\n-charset\nfilename=UTF8\n")
                for path in chunk:
                    fh.write(path + "\n")

            res = subprocess.run(
                [exiftool_path, "-@", argfile],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30 + len(chunk),
            )
            if not res.stdout:
                return {}

            data_list = json.loads(res.stdout)
            if not isinstance(data_list, list):
                return {}

            # ExifTool echoes SourceFile with forward slashes; key the chunk by a
            # normalised form so records map back to the caller's original strings.
            by_norm = {os.path.normcase(os.path.normpath(p)): p for p in chunk}
            out: Dict[str, Dict[str, Any]] = {}
            for record in data_list:
                if not isinstance(record, dict):
                    continue
                src = record.get("SourceFile")
                if not src:
                    continue
                original = by_norm.get(os.path.normcase(os.path.normpath(src)))
                if original:
                    out[original] = record
            return out
        except Exception as ex:
            logging.warning(f"Batched ExifTool extraction failed for {len(chunk)} file(s): {ex}")
            return {}
        finally:
            if argfile and os.path.exists(argfile):
                try:
                    os.remove(argfile)
                except OSError:
                    pass

    @classmethod
    def extract_full_metadata(cls, file_path: str) -> Dict[str, Any]:
        """
        Extracts comprehensive EXIF (photos) or MediaInfo (videos) metadata tags.
        Returns a dictionary with structured attribute values and 'raw_json'.

        Single-file path. For more than a couple of files prefer
        extract_full_metadata_batch(), which amortises ExifTool's process startup.
        """
        # Tier 0: ExifTool CLI (Phil Harvey's ExifTool) if available in PATH or bin/
        exiftool_meta = cls._extract_exiftool_metadata(file_path)
        if cls._is_usable_exiftool_meta(exiftool_meta):
            return exiftool_meta

        return cls._extract_library_metadata(file_path)

    @classmethod
    def _extract_library_metadata(cls, file_path: str) -> Dict[str, Any]:
        """ExifRead / Pillow / PyMediaInfo extraction tiers (no ExifTool subprocess)."""
        meta: Dict[str, Any] = {
            "camera_make": None,
            "camera_model": None,
            "lens_model": None,
            "serial_number": None,
            "iso": None,
            "aperture": None,
            "shutter_speed": None,
            "focal_length": None,
            "white_balance": None,
            "width": None,
            "height": None,
            "aspect_ratio": None,
            "color_space": None,
            "video_codec": None,
            "container_format": None,
            "frame_rate": None,
            "duration_seconds": None,
            "bitrate": None,
            "audio_codec": None,
            "audio_channels": None,
            "audio_sample_rate": None,
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "raw_json": "{}"
        }

        ext = os.path.splitext(file_path)[1].lower()

        # 1. Image EXIF Extraction
        if ext in cls.IMAGE_EXTENSIONS:

            # 1A. ExifRead Tier
            try:
                with open(file_path, 'rb') as f:
                    tags = exifread.process_file(f, details=False)

                if tags:
                    meta["camera_make"] = str(tags.get("Image Make", "")).strip() or None
                    meta["camera_model"] = str(tags.get("Image Model", "")).strip() or None
                    
                    lens = tags.get("EXIF LensModel") or tags.get("EXIF LensInfo") or tags.get("EXIF Lens")
                    meta["lens_model"] = str(lens).strip() if lens else None
                    
                    serial = tags.get("EXIF BodySerialNumber") or tags.get("EXIF SerialNumber") or tags.get("Image SerialNumber")
                    meta["serial_number"] = str(serial).strip() if serial else None

                    iso_tag = tags.get("EXIF ISOSpeedRatings") or tags.get("EXIF PhotographicSensitivity")
                    if iso_tag:
                        try:
                            meta["iso"] = int(str(iso_tag).split()[0])
                        except Exception:
                            pass

                    aperture_tag = tags.get("EXIF FNumber") or tags.get("EXIF ApertureValue")
                    if aperture_tag:
                        fnum = _parse_exif_ratio(aperture_tag.values[0] if hasattr(aperture_tag, 'values') and aperture_tag.values else aperture_tag)
                        meta["aperture"] = f"f/{fnum:.1f}" if fnum > 0 else str(aperture_tag)

                    shutter_tag = tags.get("EXIF ExposureTime") or tags.get("EXIF ShutterSpeedValue")
                    if shutter_tag:
                        meta["shutter_speed"] = str(shutter_tag).strip()

                    focal_tag = tags.get("EXIF FocalLength")
                    if focal_tag:
                        flen = _parse_exif_ratio(focal_tag.values[0] if hasattr(focal_tag, 'values') and focal_tag.values else focal_tag)
                        meta["focal_length"] = f"{flen:.1f}mm" if flen > 0 else str(focal_tag)

                    wb_tag = tags.get("EXIF WhiteBalance")
                    if wb_tag:
                        wb_val = str(wb_tag).strip()
                        meta["white_balance"] = "Auto" if wb_val == "0" else ("Manual" if wb_val == "1" else wb_val)

                    width_tag = tags.get("EXIF ExifImageWidth") or tags.get("Image ImageWidth")
                    if width_tag:
                        try:
                            meta["width"] = int(str(width_tag).split()[0])
                        except Exception:
                            pass

                    height_tag = tags.get("EXIF ExifImageLength") or tags.get("Image ImageLength")
                    if height_tag:
                        try:
                            meta["height"] = int(str(height_tag).split()[0])
                        except Exception:
                            pass

                    if meta["width"] and meta["height"] and meta["height"] != 0:
                        meta["aspect_ratio"] = f"{meta['width']}:{meta['height']}"

                    cs_tag = tags.get("EXIF ColorSpace")
                    if cs_tag:
                        meta["color_space"] = "sRGB" if str(cs_tag) == "1" else str(cs_tag)

                    lat, lon, alt = _parse_gps_coords(tags)
                    meta["latitude"], meta["longitude"], meta["altitude"] = lat, lon, alt

                    raw_dict = {k: str(v) for k, v in tags.items()}
                    meta["raw_json"] = json.dumps(raw_dict, default=str)
            except Exception:
                pass

            # 1B. Pillow (PIL.Image) Fallback / Supplement Tier
            try:
                from PIL import Image, ExifTags
                with Image.open(file_path) as img:
                    if not meta["width"] or not meta["height"]:
                        w, h = img.size
                        meta["width"] = meta["width"] or w
                        meta["height"] = meta["height"] or h
                        if meta["width"] and meta["height"] and meta["height"] != 0:
                            meta["aspect_ratio"] = meta["aspect_ratio"] or f"{meta['width']}:{meta['height']}"

                    exif_data = img.getexif()
                    if exif_data:
                        tag_dict = {}
                        for tag_id, val in exif_data.items():
                            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                            tag_dict[tag_name] = str(val)

                            if tag_id == 271 or tag_name == 'Make':
                                meta["camera_make"] = meta["camera_make"] or str(val).strip()
                            elif tag_id == 272 or tag_name == 'Model':
                                meta["camera_model"] = meta["camera_model"] or str(val).strip()
                            elif tag_id == 42036 or tag_name in ('LensModel', 'LensInfo'):
                                meta["lens_model"] = meta["lens_model"] or str(val).strip()
                            elif tag_id == 42033 or tag_name in ('BodySerialNumber', 'SerialNumber'):
                                meta["serial_number"] = meta["serial_number"] or str(val).strip()
                            elif tag_id == 34855 or tag_name in ('ISOSpeedRatings', 'PhotographicSensitivity'):
                                if not meta["iso"]:
                                    try:
                                        meta["iso"] = int(val[0] if isinstance(val, (list, tuple)) else val)
                                    except Exception:
                                        pass
                            elif tag_id == 33437 or tag_name == 'FNumber':
                                if not meta["aperture"]:
                                    fnum = _parse_exif_ratio(val)
                                    meta["aperture"] = f"f/{fnum:.1f}" if fnum > 0 else str(val)
                            elif tag_id == 33434 or tag_name == 'ExposureTime':
                                if not meta["shutter_speed"]:
                                    meta["shutter_speed"] = str(val).strip()
                            elif tag_id == 37386 or tag_name == 'FocalLength':
                                if not meta["focal_length"]:
                                    flen = _parse_exif_ratio(val)
                                    meta["focal_length"] = f"{flen:.1f}mm" if flen > 0 else str(val)

                        if tag_dict and meta["raw_json"] == "{}":
                            meta["raw_json"] = json.dumps(tag_dict, default=str)
            except Exception:
                pass

            return meta


        # 2. Video MediaInfo Extraction
        if ext in cls.VIDEO_EXTENSIONS:
            try:
                media_info = MediaInfo.parse(file_path)
                for track in media_info.tracks:
                    if track.track_type == 'General':
                        meta["container_format"] = track.commercial_name or track.format
                        if track.duration:
                            try:
                                meta["duration_seconds"] = float(track.duration) / 1000.0
                            except Exception:
                                pass
                        if track.overall_bit_rate:
                            try:
                                meta["bitrate"] = int(track.overall_bit_rate)
                            except Exception:
                                pass
                        meta["camera_make"] = getattr(track, 'make', None)
                        meta["camera_model"] = getattr(track, 'model', None)

                    elif track.track_type == 'Video':
                        meta["video_codec"] = track.commercial_name or track.format or track.codec_id
                        if track.width:
                            try:
                                meta["width"] = int(track.width)
                            except Exception:
                                pass
                        if track.height:
                            try:
                                meta["height"] = int(track.height)
                            except Exception:
                                pass
                        if track.frame_rate:
                            try:
                                meta["frame_rate"] = float(track.frame_rate)
                            except Exception:
                                pass
                        meta["aspect_ratio"] = track.display_aspect_ratio
                        meta["color_space"] = track.color_space or track.transfer_characteristics
                        if not meta["bitrate"] and track.bit_rate:
                            try:
                                meta["bitrate"] = int(track.bit_rate)
                            except Exception:
                                pass

                    elif track.track_type == 'Audio':
                        if not meta["audio_codec"]:
                            meta["audio_codec"] = track.format or track.codec_id
                            channels = getattr(track, 'channel_s', None) or getattr(track, 'channels', None)
                            if channels:
                                try:
                                    meta["audio_channels"] = int(channels)
                                except Exception:
                                    pass
                            if track.sampling_rate:
                                try:
                                    meta["audio_sample_rate"] = int(track.sampling_rate)
                                except Exception:
                                    pass

                meta["raw_json"] = json.dumps(media_info.to_data(), default=str)
                return meta
            except Exception:
                pass

        return meta

