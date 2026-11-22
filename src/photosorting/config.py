"""Configuration management for PhotoSorting."""

import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration."""

    # File format support
    image_extensions: set[str] = field(default_factory=lambda: {
        ".jpg", ".jpeg", ".heic", ".heif", ".png",
        ".webp", ".dng", ".bmp", ".gif", ".tiff", ".tif",
    })
    video_extensions: set[str] = field(default_factory=lambda: {
        ".mov", ".mp4", ".3gp", ".m4v",
    })

    # Geo data paths (relative to package data dir)
    ne_shapefile: str = "ne_110m/ne_110m_admin_0_countries.shp"
    china_gpkg: str = "gadm41_CHN.gpkg"

    # Coordinate reference system for China cities
    # "wgs84" or "gcj02"
    china_crs: str = "wgs84"

    # Target folder naming
    location_folder_format: str = "{year}-{month:02d}·{location}"
    other_folder_format: str = "Other/{year}-{month:02d}"
    unknown_folder: str = "Unknown"

    # File naming
    file_name_format: str = "{date}_{time}{seq}.{ext}"

    # Dry-run mode
    dry_run: bool = False

    # Max concurrency for scanning
    max_scan_workers: int = 8

    # Video metadata tools (auto-detected at runtime)
    ffprobe_path: str | None = None
    exiftool_path: str | None = None

    @property
    def all_extensions(self) -> set[str]:
        return self.image_extensions | self.video_extensions

    def save(self, path: Path) -> None:
        data = {
            "image_extensions": sorted(self.image_extensions),
            "video_extensions": sorted(self.video_extensions),
            "china_crs": self.china_crs,
            "dry_run": self.dry_run,
            "max_scan_workers": self.max_scan_workers,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "Config":
        if path.exists():
            data = json.loads(path.read_text())
            config = cls()
            if "image_extensions" in data:
                config.image_extensions = set(data["image_extensions"])
            if "video_extensions" in data:
                config.video_extensions = set(data["video_extensions"])
            if "china_crs" in data:
                config.china_crs = data["china_crs"]
            if "dry_run" in data:
                config.dry_run = data["dry_run"]
            if "max_scan_workers" in data:
                config.max_scan_workers = data["max_scan_workers"]
            return config
        return cls()

    @classmethod
    def default(cls) -> "Config":
        return cls()