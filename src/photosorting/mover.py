"""File mover: organize media files into target directory structure."""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from .metadata import MediaMeta
from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class MoveResult:
    """Result of a file move operation."""
    source: Path
    target: Path
    operation: str  # "move", "copy", "copy_fallback"
    success: bool
    error: Optional[str] = None


@dataclass
class OrganizeStats:
    """Statistics for an organize operation."""
    total: int = 0
    moved: int = 0
    copied: int = 0
    failed: int = 0
    by_folder: dict[str, int] = field(default_factory=dict)
    results: list[MoveResult] = field(default_factory=list)


def compute_target_path(
    meta: MediaMeta,
    location: Optional[dict],
    output_dir: Path,
    seq_map: dict[str, int],
    config: Config,
) -> Path:
    """Compute the target path for a media file.

    Folder naming:
      - Has GPS + location: YYYY-MM·{location}/
      - Has date, no GPS: Other/YYYY-MM/
      - No date: Unknown/

    File naming: YYYYMMDD_HHMMSS[_seq].ext
    """
    dt = meta.capture_time or datetime.now()
    ext = meta.file_path.suffix.lower()

    if location and location.get("name_zh") and location["name_zh"] != "Other":
        folder = config.location_folder_format.format(
            year=dt.year, month=dt.month, location=location["name_zh"]
        )
    elif meta.capture_time:
        folder = config.other_folder_format.format(year=dt.year, month=dt.month)
    else:
        folder = config.unknown_folder

    # Build filename with sequence for duplicates
    base = dt.strftime("%Y%m%d_%H%M%S")
    key = f"{folder}/{base}{ext}"
    seq = seq_map.get(key, 0)
    if seq > 0:
        filename = f"{base}_{seq}{ext}"
    else:
        filename = f"{base}{ext}"
    seq_map[key] = seq + 1

    return output_dir / folder / filename


def move_file(source: Path, target: Path) -> MoveResult:
    """Move or copy a file to the target path.

    Tries os.rename first (fast, same filesystem).
    Falls back to shutil.copy2 + os.remove (cross-device).
    """
    operation = "move"
    success = True
    error = None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return MoveResult(source, target, "move", False, f"Failed to create target dir: {e}")

    try:
        os.rename(str(source), str(target))
        operation = "move"
    except OSError:
        try:
            shutil.copy2(str(source), str(target))
            os.remove(str(source))
            operation = "copy_fallback"
        except OSError as e:
            success = False
            error = str(e)
            # Try at least to copy if move failed
            try:
                shutil.copy2(str(source), str(target))
                operation = "copy"
                success = True
                error = None
            except OSError as e2:
                success = False
                error = f"Move failed: {e}, Copy failed: {e2}"

    return MoveResult(source, target, operation, success, error)


def organize_files(
    media_list: list[MediaMeta],
    locations: dict[int, dict],
    output_dir: Path,
    config: Config,
) -> OrganizeStats:
    """Organize media files into the target directory structure.

    Args:
        media_list: List of MediaMeta objects with resolved locations.
        locations: Dict mapping index to location info.
        output_dir: Root output directory.
        config: Application config.

    Returns:
        OrganizeStats with operation results.
    """
    stats = OrganizeStats(total=len(media_list))
    seq_map: dict[str, int] = {}

    for i, meta in enumerate(media_list):
        loc = locations.get(i)
        target = compute_target_path(meta, loc, output_dir, seq_map, config)

        if config.dry_run:
            result = MoveResult(meta.file_path, target, "dry_run", True)
        else:
            result = move_file(meta.file_path, target)

        stats.results.append(result)
        if result.success:
            if result.operation == "move":
                stats.moved += 1
            else:
                stats.copied += 1
            # Track by folder
            folder_name = str(target.parent.relative_to(output_dir))
            stats.by_folder[folder_name] = stats.by_folder.get(folder_name, 0) + 1
        else:
            stats.failed += 1
            logger.error(f"Failed for {meta.file_path}: {result.error}")

    return stats