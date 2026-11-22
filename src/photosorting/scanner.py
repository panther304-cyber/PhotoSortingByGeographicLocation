"""File scanner: discover and extract metadata from media files."""

import logging
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

from .config import Config
from .metadata import extract_metadata, MediaMeta, detect_video_tool

logger = logging.getLogger(__name__)


class ScanResult:
    """Result of scanning a source directory."""

    def __init__(self):
        self.media: list[MediaMeta] = []
        self.live_photo_pairs: list[tuple[MediaMeta, MediaMeta]] = []  # (primary, secondary)
        self.total_files: int = 0
        self.skipped_files: int = 0
        self.errors: list[tuple[Path, str]] = []


def _is_media_file(file_path: Path, config: Config) -> bool:
    """Check if a file has a supported media extension."""
    ext = file_path.suffix.lower()
    return ext in config.all_extensions


def _detect_live_photo_pairs(files: list[Path]) -> dict[str, list[Path]]:
    """Group files by base name to detect Live Photo pairs (same stem, different ext)."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        groups[f.stem.lower()].append(f)
    # Keep only groups with exactly 2 files
    return {k: v for k, v in groups.items() if len(v) == 2}


def scan_directory(source_dir: Path, config: Config) -> ScanResult:
    """Scan a directory recursively and extract metadata from all media files.

    Phase 1: Walk files, filter by extension, detect Live Photo pairs.
    Phase 2 (parallel): Extract metadata from each file.
    """
    result = ScanResult()
    source_dir = source_dir.resolve()
    logger.info(f"Scanning directory: {source_dir}")

    # Phase 1: Discover files
    all_media: list[Path] = []
    for file_path in source_dir.rglob("*"):
        result.total_files += 1
        if file_path.is_file() and _is_media_file(file_path, config):
            all_media.append(file_path)
        else:
            result.skipped_files += 1

    if not all_media:
        logger.warning("No supported media files found")
        return result

    logger.info(f"Found {len(all_media)} media files out of {result.total_files} total")

    # Detect Live Photo pairs
    pairs = _detect_live_photo_pairs(all_media)
    paired_stems = set(pairs.keys())
    standalone = [f for f in all_media if f.stem.lower() not in paired_stems]

    # Detect video tool once
    video_tool = detect_video_tool()
    if video_tool:
        logger.info(f"Using video tool: {video_tool}")
    else:
        logger.warning("No video metadata tool found (ffprobe/exiftool). Video GPS will be unavailable.")

    # Phase 2: Extract metadata in parallel
    metas: dict[Path, MediaMeta] = {}

    with ThreadPoolExecutor(max_workers=config.max_scan_workers) as executor:
        futures = {}
        for f in all_media:
            futures[executor.submit(partial(extract_metadata, video_tool=video_tool), f)] = f

        for future in as_completed(futures):
            f = futures[future]
            try:
                meta = future.result()
                metas[f] = meta
            except Exception as e:
                logger.error(f"Failed to extract metadata from {f}: {e}")
                result.errors.append((f, str(e)))

    # Phase 3: Build results with Live Photo pairing
    processed_stems = set()

    # Process Live Photo pairs
    for stem, file_list in pairs.items():
        photo = next((f for f in file_list if f.suffix.lower() in config.image_extensions), None)
        video = next((f for f in file_list if f.suffix.lower() in config.video_extensions), None)
        if photo and video and photo in metas:
            # Use photo metadata as primary, video follows
            primary_meta = metas[photo]
            secondary_meta = metas.get(video)
            if secondary_meta:
                # Video inherits photo's capture time and GPS
                secondary_meta.capture_time = primary_meta.capture_time
                secondary_meta.time_source = "live_photo_pair"
                secondary_meta.latitude = primary_meta.latitude
                secondary_meta.longitude = primary_meta.longitude
                secondary_meta.has_gps = primary_meta.has_gps
            result.live_photo_pairs.append((primary_meta, secondary_meta) if secondary_meta else (primary_meta, primary_meta))
            result.media.append(primary_meta)
            if secondary_meta:
                result.media.append(secondary_meta)
            processed_stems.add(stem)

    # Process standalone files
    for f in standalone:
        if f in metas:
            result.media.append(metas[f])

    logger.info(f"Scan complete: {len(result.media)} metadata entries, {len(result.live_photo_pairs)} Live Photo pairs")
    return result