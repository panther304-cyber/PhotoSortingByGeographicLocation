"""Metadata extraction from photos and videos."""

import os
import re
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import pillow_heif

from .gps_utils import convert_gps_to_decimal

logger = logging.getLogger(__name__)

# Pillow cannot decode HEIC/HEIF without this plugin registered.
pillow_heif.register_heif_opener()

_DATE_PATTERNS = [
    re.compile(r"(\d{4})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})"),
    re.compile(r"(\d{4})-(\d{2})-(\d{2})[T_ ](\d{2})[.:-](\d{2})[.:-](\d{2})"),
    re.compile(r"(\d{4})(\d{2})(\d{2})"),
]

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".3gp", ".m4v", ".avi", ".mkv", ".wmv", ".mts", ".m2ts"}


class MediaMeta:
    """Extracted metadata for a media file."""

    __slots__ = (
        "file_path", "capture_time", "time_source",
        "latitude", "longitude", "has_gps",
        "media_type", "file_size",
    )

    def __init__(
        self,
        file_path: Path,
        capture_time: Optional[datetime] = None,
        time_source: str = "unknown",
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        media_type: str = "unknown",
        file_size: int = 0,
    ):
        self.file_path = file_path
        self.capture_time = capture_time
        self.time_source = time_source
        self.latitude = latitude
        self.longitude = longitude
        self.has_gps = latitude is not None and longitude is not None
        self.media_type = media_type
        self.file_size = file_size

    def __repr__(self) -> str:
        return (
            f"MediaMeta(path={self.file_path.name}, "
            f"time={self.capture_time}, gps=({self.latitude}, {self.longitude}))"
        )


_EXIF_DATE_TAGS =(36867, 36868, 306)  # DateTimeOriginal, DateTimeDigitized, DateTime
_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825


def _parse_exif_datetime(value) -> Optional[datetime]:
    """Parse an EXIF date string, ignoring sub-second and timezone suffixes."""
    if value is None:
        return None
    text = str(value).strip().strip("\x00").strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def extract_image_metadata(file_path: Path) -> dict:
    """Extract EXIF metadata from an image file using Pillow."""
    result = {"capture_time": None, "latitude": None, "longitude": None, "time_source": "unknown"}

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return result

            # DateTimeOriginal/DateTimeDigitized live in the Exif sub-IFD (0x8769),
            # while DateTime is in the top-level IFD. Check both, keeping the
            # tag priority (original > digitized > modified) across IFDs.
            try:
                exif_ifd = exif.get_ifd(_EXIF_IFD)
            except Exception:
                exif_ifd = {}

            for tag_id in _EXIF_DATE_TAGS:
                dt = _parse_exif_datetime(exif_ifd.get(tag_id))
                if dt is None:
                    dt = _parse_exif_datetime(exif.get(tag_id))
                if dt is not None:
                    result["capture_time"] = dt
                    result["time_source"] = "exif"
                    break

            gps_ifd = exif.get_ifd(_GPS_IFD)
            if gps_ifd:
                gps_dict = {GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}
                lat = convert_gps_to_decimal(gps_dict.get("GPSLatitude"), str(gps_dict.get("GPSLatitudeRef", "N")))
                lon = convert_gps_to_decimal(gps_dict.get("GPSLongitude"), str(gps_dict.get("GPSLongitudeRef", "E")))
                if lat is not None and lon is not None:
                    result["latitude"] = lat
                    result["longitude"] = lon
    except Exception as e:
        logger.debug(f"Failed to read EXIF from {file_path}: {e}")

    return result


def detect_video_tool() -> Optional[str]:
    """Detect available video metadata tool (ffprobe or exiftool)."""
    for tool in ["ffprobe", "exiftool"]:
        try:
            result = subprocess.run([tool, "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                logger.info(f"Detected video tool: {tool}")
                return tool
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None
def _parse_iso6709_location(location_str: str) -> tuple[float, float] | None:
    """Parse ISO 6709 location string like '+37.7869-122.3994+5.000/' to (lat, lon)."""
    m = re.match(r"([+-]?\d+\.?\d*)([+-]\d+\.?\d*)", str(location_str))
    if m:
        return float(m.group(1)), float(m.group(2))
    return None


def _extract_gps_from_ffprobe(data: dict) -> tuple[float, float] | None:
    """Extract GPS coordinates from ffprobe JSON output.

    Checks both format-level and stream-level tags for location data,
    including Apple QuickTime ISO 6709 metadata.
    """
    # Check format-level tags first
    fmt_tags = data.get("format", {}).get("tags", {}) if isinstance(data.get("format"), dict) else {}
    for key in ("location", "com.apple.quicktime.location.ISO6709",
                "com.apple.quicktime.location.astronomicalbody"):
        if fmt_tags.get(key):
            coords = _parse_iso6709_location(fmt_tags[key])
            if coords:
                return coords

    # Then check stream-level tags
    for stream in data.get("streams", []) or []:
        st_tags = stream.get("tags", {}) if isinstance(stream.get("tags"), dict) else {}
        for key in ("location", "com.apple.quicktime.location.ISO6709"):
            if st_tags.get(key):
                coords = _parse_iso6709_location(st_tags[key])
                if coords:
                    return coords

    return None


def extract_video_metadata(file_path: Path, tool: Optional[str] = None) -> dict:
    """Extract metadata from a video file using ffprobe or exiftool.

    Returns dict with keys: capture_time, latitude, longitude, time_source.
    GPS coordinates are returned in WGS-84 decimal degrees.
    """
    result = {"capture_time": None, "latitude": None, "longitude": None, "time_source": "unknown"}
    if tool is None:
        tool = detect_video_tool()
    if tool is None:
        return result

    try:
        if tool == "ffprobe":
            proc = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", "-show_streams", str(file_path)],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                return result
            data = json.loads(proc.stdout)

            # Extract capture time from format tags
            fmt_tags = data.get("format", {}).get("tags", {}) if isinstance(data.get("format"), dict) else {}
            dt_str = fmt_tags.get("creation_time") or fmt_tags.get("date")
            if dt_str:
                for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
                    try:
                        result["capture_time"] = datetime.strptime(dt_str, fmt)
                        result["time_source"] = "ffprobe"
                        break
                    except ValueError:
                        pass

            # Extract GPS from streams and format tags
            gps_coords = _extract_gps_from_ffprobe(data)
            if gps_coords:
                result["latitude"], result["longitude"] = gps_coords

        elif tool == "exiftool":
            # Use -n flag for numeric GPS values (avoids DMS string parsing issues)
            proc = subprocess.run(
                ["exiftool", "-n", "-json",
                 "-DateTimeOriginal", "-CreateDate",
                 "-GPSLatitude", "-GPSLongitude",
                 "-GPSCoordinates",
                 "-QuickTime:GPSCoordinates",
                 str(file_path)],
                capture_output=True, text=True, timeout=15,
            )
            if proc.returncode != 0:
                return result
            data = json.loads(proc.stdout)
            if data and isinstance(data, list) and len(data) > 0:
                item = data[0]
                dt_str = item.get("DateTimeOriginal") or item.get("CreateDate")
                if dt_str:
                    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                        try:
                            result["capture_time"] = datetime.strptime(
                                str(dt_str).split("+")[0].strip(), fmt
                            )
                            result["time_source"] = "exiftool"
                            break
                        except ValueError:
                            pass

                # GPSLatitude/GPSLongitude — numeric with -n flag
                lat = item.get("GPSLatitude")
                lon = item.get("GPSLongitude")
                if lat is not None and lon is not None:
                    try:
                        result["latitude"] = float(lat)
                        result["longitude"] = float(lon)
                    except (ValueError, TypeError):
                        pass

                # QuickTime GPSCoordinates as fallback (e.g. "+37.7869-122.3994")
                if result["latitude"] is None:
                    qt_coords = item.get("GPSCoordinates") or item.get("QuickTime:GPSCoordinates")
                    if qt_coords:
                        parsed = _parse_iso6709_location(str(qt_coords))
                        if parsed:
                            result["latitude"], result["longitude"] = parsed

    except subprocess.TimeoutExpired:
        logger.warning(f"Video metadata timed out for {file_path}")
    except Exception as e:
        logger.warning(f"Error extracting video metadata from {file_path}: {e}")

    return result


def extract_date_from_filename(file_path: Path) -> Optional[datetime]:
    """Try to parse date from filename patterns."""
    name = file_path.stem
    for pattern in _DATE_PATTERNS:
        match = pattern.search(name)
        if match:
            groups = match.groups()
            try:
                if len(groups) >= 6:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]),
                                    int(groups[3]), int(groups[4]), int(groups[5]))
                elif len(groups) >= 3:
                    return datetime(int(groups[0]), int(groups[1]), int(groups[2]))
            except ValueError:
                continue
    return None


def get_file_mtime(file_path: Path) -> datetime:
    """Get file modification time as fallback."""
    return datetime.fromtimestamp(os.path.getmtime(file_path))


def is_video_file(file_path: Path) -> bool:
    """Check if file is a video based on extension."""
    return file_path.suffix.lower() in _VIDEO_EXTENSIONS


def extract_metadata(file_path: Path, video_tool: Optional[str] = None) -> MediaMeta:
    """Extract all available metadata from a media file.
    Priority: EXIF > filename > mtime

    Args:
        file_path: Path to the media file.
        video_tool: Pre-detected video tool ('ffprobe' or 'exiftool') to avoid
                    redundant detection per file. Auto-detects if None.
    """
    file_size = file_path.stat().st_size
    is_vid = is_video_file(file_path)
    media_type = "video" if is_vid else "photo"

    meta = MediaMeta(file_path=file_path, media_type=media_type, file_size=file_size)

    if is_vid:
        md = extract_video_metadata(file_path, tool=video_tool)
    else:
        md = extract_image_metadata(file_path)

    if md["capture_time"]:
        meta.capture_time = md["capture_time"]
        meta.time_source = md["time_source"]
    if md["latitude"] is not None and md["longitude"] is not None:
        meta.latitude = md["latitude"]
        meta.longitude = md["longitude"]
        meta.has_gps = True

    if meta.capture_time is None:
        fn_date = extract_date_from_filename(file_path)
        if fn_date:
            meta.capture_time = fn_date
            meta.time_source = "filename"

    if meta.capture_time is None:
        meta.capture_time = get_file_mtime(file_path)
        meta.time_source = "mtime"

    return meta