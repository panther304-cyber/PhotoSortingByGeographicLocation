"""
PhotoSorting Nuitka build script.

Produces a standalone executable (onefile or onefolder) with embedded
data files (GeoPackage, shapefiles).

Usage:
    # Install build deps first
    uv sync --group dev

    # One-folder (recommended: faster startup, larger size)
    uv run python build_nuitka.py

    # One-file (single .exe, slower startup on first run)
    uv run python build_nuitka.py --onefile

Note on DuckDB + Nuitka:
    DuckDB ships native libraries that Nuitka must include. If the build
    fails with missing DLL/extension errors, try:
      1. Use --onefolder mode (less aggressive bundling)
      2. Alternatively, fall back to PyInstaller:
           uvx pyinstaller --onefile --add-data "data;data" src/photosorting/cli.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLI_ENTRY = ROOT / "src" / "photosorting" / "cli.py"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "dist"


def run_nuitka(onefile: bool = False) -> None:
    """Build with Nuitka standalone mode."""
    mode_flag = "--onefile" if onefile else "--standalone"
    output_name = "PhotoSorting.exe" if onefile else "PhotoSorting"

    cmd = [
        sys.executable, "-m", "nuitka",
        mode_flag,
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={output_name}",
        f"--include-data-dir={DATA_DIR}=data",
        "--include-package=photosorting",
        "--include-package=pillow_heif",
        "--include-package=duckdb",
        "--include-module=_duckdb",
        "--enable-plugin=anti-bloat",
        "--assume-yes-for-downloads",
        "--windows-console-mode=force",
        str(CLI_ENTRY),
    ]

    print(f"[build] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    sys.exit(result.returncode)


if __name__ == "__main__":
    onefile = "--onefile" in sys.argv
    run_nuitka(onefile=onefile)