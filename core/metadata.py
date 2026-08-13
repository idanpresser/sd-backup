"""
Metadata Engine & Composite Hasher for SD-FastBackup.
Extracts Date Taken via EXIF (including RAW formats), PyMediaInfo, or mtime fallback, and computes fast composite SHA256 hashes.
"""
import os
import json
import hashlib
from datetime import datetime
from typing import Tuple, Dict, Any, Optional
import exifread
from pymediainfo import MediaInfo


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

    @classmethod
    def extract_full_metadata(cls, file_path: str) -> Dict[str, Any]:
        """
        Extracts comprehensive EXIF (photos) or MediaInfo (videos) metadata tags.
        Returns a dictionary with structured attribute values and 'raw_json'.
        """
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
                    return meta
            except Exception:
                pass

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

