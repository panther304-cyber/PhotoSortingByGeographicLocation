"""CLI entry point with Rich TUI for PhotoSorting.

Supports two modes:
  1. Interactive mode (default): prompts for paths and options via Rich TUI.
  2. Non-interactive mode: use --source/--output etc. for scripting/automation.
"""

import argparse
import logging
import os as _os
import shutil as _shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Prompt, Confirm

try:
    from .config import Config
    from .scanner import scan_directory
    from .geo_resolver import GeoResolver
    from .mover import OrganizeStats, MoveResult, compute_target_path
except ImportError:
    from photosorting.config import Config
    from photosorting.scanner import scan_directory
    from photosorting.geo_resolver import GeoResolver
    from photosorting.mover import OrganizeStats, MoveResult, compute_target_path

logger = logging.getLogger(__name__)
console = Console()


def _get_package_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data"


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]📸 PhotoSorting[/bold cyan] — "
        "[dim]iPhone/Android 照片整理工具 v0.1.0[/dim]",
        border_style="cyan",
    ))


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for non-interactive mode."""
    parser = argparse.ArgumentParser(
        prog="photosorting",
        description="iPhone/Android 照片整理工具 — 按拍摄时间和地点自动归类",
    )
    parser.add_argument(
        "--source", "-s",
        type=str, default=None,
        help="源文件夹路径（照片导出所在目录）",
    )
    parser.add_argument(
        "--output", "-o",
        type=str, default=None,
        help="目标文件夹路径（整理后输出目录，默认 <source>_整理后）",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true", default=False,
        help="试运行模式：仅分析不移动文件",
    )
    parser.add_argument(
        "--china-crs",
        type=str, choices=["wgs84", "gcj02"], default=None,
        help="中国城市数据坐标系 (默认 wgs84)，gcj02 时自动将照片 GPS 转为火星坐标再匹配",
    )
    parser.add_argument(
        "--config", "-c",
        type=str, default=None,
        help="JSON 配置文件路径",
    )
    parser.add_argument(
        "--log-level",
        type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别 (默认 INFO)",
    )
    parser.add_argument(
        "--version", "-V",
        action="store_true", default=False,
        help="显示版本号并退出",
    )
    return parser


def prompt_paths() -> tuple[Path, Path, bool]:
    console.print()
    source_str = Prompt.ask("[bold]源文件夹路径[/bold] (导出照片所在目录)", default=".")
    source = Path(source_str).resolve()
    if not source.exists():
        console.print(f"[red]错误: 路径不存在 - {source}[/red]")
        sys.exit(1)
    if not source.is_dir():
        console.print(f"[red]错误: 不是目录 - {source}[/red]")
        sys.exit(1)

    output_str = Prompt.ask(
        "[bold]目标文件夹路径[/bold] (整理后输出目录)",
        default=str(source.parent / (source.name + "_整理后")),
    )
    output = Path(output_str).resolve()
    dry_run = Confirm.ask("[bold]试运行模式[/bold]? (仅分析不移动)", default=False)
    return source, output, dry_run
def build_folder_summary_table(stats: OrganizeStats) -> Table:
    table = Table(title="📊 整理结果汇总", border_style="green")
    table.add_column("目标文件夹", style="cyan", no_wrap=True)
    table.add_column("文件数", justify="right", style="yellow")
    table.add_column("占比", justify="right", style="dim")

    for folder, count in sorted(stats.by_folder.items(), key=lambda x: -x[1]):
        pct = count / max(stats.total, 1) * 100
        table.add_row(folder, str(count), f"{pct:.1f}%")

    table.add_section()
    table.add_row("[bold]总计[/bold]", f"[bold]{stats.total}[/bold]", "[bold]100%[/bold]")
    return table


def build_result_table(stats: OrganizeStats, dry_run: bool = False) -> Table:
    if dry_run:
        table = Table(title="📋 试运行结果 (未移动任何文件)", border_style="yellow")
        table.add_column("分析项", style="cyan")
        table.add_column("数量", justify="right", style="yellow")
        table.add_row("📊 分析文件总数", str(stats.total))
        table.add_row("📁 目标文件夹数", str(len(stats.by_folder)))
        return table

    table = Table(title="📋 操作详情", border_style="blue")
    table.add_column("操作", style="green")
    table.add_column("数量", justify="right", style="yellow")
    table.add_row("✅ 移动成功 (rename)", str(stats.moved))
    table.add_row("📋 复制成功 (cross-device)", str(stats.copied))
    table.add_row("❌ 失败", f"[red]{stats.failed}[/red]" if stats.failed else "0")
    table.add_row("[bold]总计[/bold]", f"[bold]{stats.total}[/bold]")
    return table


def _move_single_file(source: Path, target: Path) -> MoveResult:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _os.rename(str(source), str(target))
        return MoveResult(source, target, "move", True)
    except OSError:
        try:
            _shutil.copy2(str(source), str(target))
            _os.remove(str(source))
            return MoveResult(source, target, "copy_fallback", True)
        except OSError as e:
            try:
                _shutil.copy2(str(source), str(target))
                return MoveResult(source, target, "copy", True)
            except OSError as e2:
                return MoveResult(source, target, "move", False, str(e2))
def run_pipeline(source: Path, output: Path, config: Config):
    """Run the full photo sorting pipeline with progress display."""
    data_dir = _get_package_data_dir()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        # Stage 1: Scan
        scan_task = progress.add_task("[cyan]阶段 1/4: 扫描文件并提取元数据...", total=100)
        scan_result = scan_directory(source, config)
        n = len(scan_result.media)
        progress.update(scan_task, completed=100,
                        description=f"[green]✅ 扫描完成: {n} 个文件")

        if not scan_result.media:
            console.print("[yellow]没有找到支持的媒体文件[/yellow]")
            return

        # Stage 2: Geo matching
        geo_task = progress.add_task("[cyan]阶段 2/4: 地理匹配...", total=100)
        geo = GeoResolver(config, data_dir)
        coords_to_resolve = []

        for i, meta in enumerate(scan_result.media):
            if meta.has_gps and meta.latitude is not None and meta.longitude is not None:
                lat, lon = geo.convert_coords_for_china(meta.latitude, meta.longitude)
                coords_to_resolve.append((i, lat, lon))

        progress.update(geo_task, advance=30,
                        description=f"[cyan]地理匹配: {len(coords_to_resolve)} 个GPS坐标...")

        location_map = {}
        if coords_to_resolve:
            location_map = geo.resolve_batch(coords_to_resolve)
            progress.update(geo_task, advance=70,
                            description=f"[green]✅ 地理匹配 ({len(location_map)} 个)")
        else:
            progress.update(geo_task, advance=70,
                            description="[dim]无GPS坐标, 跳过")

        geo.close()
        progress.update(geo_task, completed=100)

        # Stage 3: Organize files
        move_task = progress.add_task(
            "[cyan]阶段 3/4: 整理文件...", total=len(scan_result.media)
        )

        all_locations = {}
        for i in range(len(scan_result.media)):
            all_locations[i] = location_map.get(i, {
                "name_zh": "Other", "level": "other", "province": None
            })

        stats = OrganizeStats(total=len(scan_result.media))
        seq_map = {}

        for i, meta in enumerate(scan_result.media):
            loc = all_locations.get(i)
            target = compute_target_path(meta, loc, output, seq_map, config)

            if config.dry_run:
                result = MoveResult(meta.file_path, target, "dry_run", True)
                stats.results.append(result)
                folder_name = str(target.parent.relative_to(output))
                stats.by_folder[folder_name] = stats.by_folder.get(folder_name, 0) + 1
            else:
                result = _move_single_file(meta.file_path, target)
                stats.results.append(result)
                if result.success:
                    if result.operation == "move":
                        stats.moved += 1
                    else:
                        stats.copied += 1
                    folder_name = str(target.parent.relative_to(output))
                    stats.by_folder[folder_name] = stats.by_folder.get(folder_name, 0) + 1
                else:
                    stats.failed += 1

            progress.update(move_task, advance=1,
                            description=f"[cyan]整理: {i+1}/{len(scan_result.media)}")

        progress.update(move_task, completed=100,
                        description="[green]✅ 文件整理完成")

    # Print summary
    console.print()
    console.print(build_result_table(stats, dry_run=config.dry_run))
    console.print()
    console.print(build_folder_summary_table(stats))

    if stats.failed > 0:
        console.print(f"\n[red]⚠️ {stats.failed} 个文件处理失败[/red]")


def main():
    """Main entry point.

    When --source is not provided, runs in interactive mode with Rich TUI prompts.
    Otherwise runs non-interactively with the given arguments.
    """
    parser = build_parser()
    args = parser.parse_args()

    # --version
    if args.version:
        try:
            from . import __version__
        except ImportError:
            from photosorting import __version__
        print(f"PhotoSorting v{__version__}")
        sys.exit(0)

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── Non-interactive mode ──
    if args.source:
        return _run_noninteractive(args)

    # ── Interactive mode (default) ──
    print_banner()
    source, output, dry_run = prompt_paths()

    config = Config.default()
    config.dry_run = dry_run

    console.print(f"\n[dim]源文件夹: {source}[/dim]")
    console.print(f"[dim]目标文件夹: {output}[/dim]")
    console.print(f"[dim]模式: {'Dry-Run (仅分析)' if dry_run else '正式整理'}[/dim]")

    if not dry_run:
        if output.resolve() == source.resolve():
            console.print("[red]错误: 源文件夹和目标文件夹不能相同[/red]")
            sys.exit(1)

    console.print()
    run_pipeline(source, output, config)
    console.print()
    console.print("[bold green]✨ 完成![/bold green]")


def _run_noninteractive(args) -> None:
    """Run in non-interactive (CLI argument) mode."""
    source = Path(args.source).resolve()
    if not source.exists():
        console.print(f"[red]错误: 路径不存在 - {source}[/red]")
        sys.exit(1)
    if not source.is_dir():
        console.print(f"[red]错误: 不是目录 - {source}[/red]")
        sys.exit(1)

    if args.output:
        output = Path(args.output).resolve()
    else:
        output = source.parent / (source.name + "_整理后")

    # Load config file if provided, else use defaults
    if args.config:
        config = Config.load(Path(args.config))
    else:
        config = Config.default()

    # Override from CLI args
    config.dry_run = args.dry_run
    if args.china_crs:
        config.china_crs = args.china_crs

    print_banner()
    console.print(f"\n[dim]源文件夹: {source}[/dim]")
    console.print(f"[dim]目标文件夹: {output}[/dim]")
    console.print(f"[dim]模式: {'Dry-Run (仅分析)' if config.dry_run else '正式整理'}[/dim]")
    console.print(f"[dim]坐标系: {config.china_crs.upper()}[/dim]")
    if args.config:
        console.print(f"[dim]配置文件: {args.config}[/dim]")

    if not config.dry_run:
        if output.resolve() == source.resolve():
            console.print("[red]错误: 源文件夹和目标文件夹不能相同[/red]")
            sys.exit(1)

    console.print()
    run_pipeline(source, output, config)
    console.print()
    console.print("[bold green]✨ 完成![/bold green]")