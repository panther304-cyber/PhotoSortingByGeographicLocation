# PhotoSorting

PhotoSorting is a command-line tool for organizing photos and videos exported from iPhones, Android phones, cameras, and mixed media folders. It reads capture metadata, resolves GPS coordinates to a city or country, and moves files into a predictable `year-month/location` structure.

The tool supports interactive and non-interactive workflows, including a dry-run mode for previewing the result before moving anything.

## Features

- Extracts capture times from image EXIF, video metadata, filenames, and file modification times.
- Resolves GPS coordinates to Chinese prefecture-level cities and non-Chinese countries.
- Supports WGS-84 and GCJ-02 coordinate matching for Chinese boundary data.
- Detects matching Live Photo image/video pairs and uses the image as the metadata source.
- Scans and extracts media metadata concurrently.
- Provides an interactive Rich terminal UI and a script-friendly CLI.
- Supports HEIC and HEIF images through Pillow and `pillow-heif`.
- Includes a Nuitka build script for standalone distributions.

## Supported formats

| Type | Formats |
| --- | --- |
| Images | `.jpg`, `.jpeg`, `.heic`, `.heif`, `.png`, `.webp`, `.dng`, `.bmp`, `.gif`, `.tiff`, `.tif` |
| Videos | `.mov`, `.mp4`, `.3gp`, `.m4v` |

You can extend the recognized extensions through a JSON configuration file.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Optional: `ffprobe` or `exiftool` for video capture time and GPS metadata
- Network access for the first geographic-data download and, when no bundled DuckDB extension is available, for installing DuckDB Spatial

## Installation

```bash
git clone <repository-url> PhotoSorting
cd PhotoSorting
uv sync
```

Prepare the geographic boundary data on first use:

```bash
uv run python prepare_geo_data.py
```

The preparation script downloads:

- Natural Earth 110m country boundaries
- GADM 4.1 China administrative boundaries

The resulting data is stored under `data/`.

## Usage

### Interactive mode

Start the Rich terminal UI:

```bash
uv run photosorting
```

The UI prompts for:

- Source directory
- Output directory
- Whether to run in dry-run mode

### Command-line mode

```bash
# Organize files
uv run photosorting --source ./Sample --output ./Output

# Preview destinations without moving files
uv run photosorting --source ./Sample --dry-run

# Match against GCJ-02 China boundary data
uv run photosorting --source ./Sample --china-crs gcj02

# Load a JSON configuration file and enable debug logging
uv run photosorting --source ./Sample --config config.json --log-level DEBUG

# Show the installed version
uv run photosorting --version
```

If `--output` is omitted, the default destination is a sibling directory derived from the source directory name. The current implementation uses `<source>_整理后`.

> **Important:** use `--dry-run` to preview the operation. Without it, files are moved. In CLI mode, the current implementation always overrides the JSON `dry_run` field from the command-line value, so `--dry-run` is the reliable non-interactive option.

## Output layout

Files with GPS coordinates are grouped by capture month and resolved location. Files without a resolved location but with a capture time are grouped by month under `Other/`.

```text
Output/
├── 2025-10·Shenzhen/
│   ├── 20251001_143025.jpg
│   ├── 20251001_143025.mov
│   └── 20251001_143026.jpg
├── 2025-10·Beijing/
│   └── 20251003_091200.jpg
└── Other/2025-10/
    └── 20251005_120000.png
```

Files are renamed as:

```text
YYYYMMDD_HHMMSS[_sequence].extension
```

A numeric suffix is added when multiple files in the same destination folder share the same timestamp and extension.

## Metadata behavior

Capture time is selected in this order:

1. Image EXIF or video metadata
2. Date parsed from the filename
3. File modification time

For a detected Live Photo pair, the image metadata is treated as authoritative. The video inherits the image's capture time and GPS coordinates so both files belong to the same location folder.

Video metadata requires `ffprobe` or `exiftool` to be available on `PATH`. If neither tool is installed, video files still receive filename or modification-time dates, but video GPS resolution is unavailable.

## Configuration

Create a JSON file such as `config.json`:

```json
{
  "china_crs": "wgs84",
  "dry_run": false,
  "max_scan_workers": 8,
  "image_extensions": [
    ".jpg",
    ".jpeg",
    ".heic",
    ".heif",
    ".png",
    ".webp",
    ".dng",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif"
  ],
  "video_extensions": [
    ".mov",
    ".mp4",
    ".3gp",
    ".m4v"
  ]
}
```

| Field | Description | Default |
| --- | --- | --- |
| `china_crs` | Coordinate system of the China boundary data: `wgs84` or `gcj02` | `wgs84` |
| `dry_run` | Stored dry-run default; use `--dry-run` in CLI mode | `false` |
| `max_scan_workers` | Number of concurrent metadata-extraction workers | `8` |
| `image_extensions` | Recognized image filename extensions | Built-in list |
| `video_extensions` | Recognized video filename extensions | Built-in list |

`--china-crs` overrides the corresponding configuration value. The current CLI also overrides `dry_run`; see the usage note above.

## Coordinate systems

Photo GPS tags normally use WGS-84. If the China boundary data also uses WGS-84, keep `china_crs` set to `wgs84`.

If the boundary data uses GCJ-02, set:

```bash
uv run photosorting --source ./photos --china-crs gcj02
```

PhotoSorting converts WGS-84 photo coordinates to GCJ-02 before performing the spatial lookup. Locations outside the supported China bounding box are left unchanged.

## Processing pipeline

1. Recursively discover supported image and video files.
2. Detect same-name image/video pairs that qualify as Live Photos.
3. Extract metadata concurrently.
4. Resolve GPS coordinates in a single DuckDB Spatial batch query.
5. Compute target folders and collision-free filenames.
6. Move files, or report the planned destinations during a dry run.
7. Print operation and destination-folder summaries.

When moving across devices, the tool attempts `rename` first and falls back to copy-then-delete.

## Build a standalone application

Install the development dependencies:

```bash
uv sync --group dev
```

Build a one-folder distribution, which is the recommended mode for faster startup:

```bash
uv run python build_nuitka.py
```

Build a single executable:

```bash
uv run python build_nuitka.py --onefile
```

DuckDB includes native libraries. If a one-file build has DLL-loading problems, use the one-folder build.

## Project structure

```text
PhotoSorting/
├── src/photosorting/
│   ├── cli.py            # Interactive and command-line entry point
│   ├── config.py         # Configuration model and JSON loading
│   ├── metadata.py       # Image and video metadata extraction
│   ├── scanner.py        # Media discovery and Live Photo pairing
│   ├── geo_resolver.py   # DuckDB Spatial boundary lookup
│   ├── gps_utils.py      # WGS-84 / GCJ-02 conversion
│   └── mover.py          # Target-path calculation and file operations
├── data/                 # Geographic boundary data
├── docs/                 # Domain model, glossary, and architecture decisions
├── build_nuitka.py       # Standalone build script
├── prepare_geo_data.py   # Geographic-data preparation script
├── pyproject.toml        # Project metadata and dependencies
└── uv.lock               # Resolved dependency lockfile
```

## Troubleshooting

**No supported media files were found**

Confirm that the source directory contains one of the supported extensions and that the extension is enabled in the configuration.

**Video GPS is unavailable**

Install `ffprobe` or `exiftool` and make sure the executable is available on `PATH`.

**DuckDB Spatial cannot be loaded**

Run `prepare_geo_data.py` again and verify that `data/duckdb_extensions` exists. Otherwise, allow DuckDB to install its Spatial extension.

**HEIC files are not recognized**

Run `uv sync` so that `pillow-heif` is installed. Rebuild a standalone package after changing dependencies.

## License

MIT
