# 📸 PhotoSorting

**iPhone/Android 照片整理工具** — 按拍摄时间和地点自动归类。

> 从手机导出的混杂文件夹 → 一键整理为 `YYYY-MM·城市/YYYYMMDD_HHMMSS.ext` 结构

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 功能特性

- **📅 时间提取** — 照片 EXIF、视频 ffprobe/exiftool、文件名解析、文件 mtime 多级回退
- **🌍 GPS 地理匹配** — DuckDB Spatial 精确到城市级（中国大陆）和国家级的归属判断
- **🇨🇳 GCJ-02 火星坐标** — 内置 WGS-84 ↔ GCJ-02 双向转换，兼容国内外地图数据
- **📱 Live Photo** — 自动配对同名照片+视频，以照片为主源统一归类
- **⚡ 并发扫描** — 多线程并发提取元数据，大幅加速
- **🔍 Dry-Run** — 试运行模式，预览分类结果而不实际移动文件
- **🖥️ CLI 双模式** — 交互式 Rich TUI + 命令行参数非交互模式

---

## 📦 快速开始

### 前置依赖

| 工具 | 用途 | 必须? |
|------|------|-------|
| Python 3.12+ | 运行环境 | ✅ |
| uv | 包管理器 | ✅ |
| ffprobe | 视频 GPS/时间提取（推荐） | 可选 |
| exiftool | 视频元数据提取（回退） | 可选 |

### 安装

```bash
# 克隆仓库
git clone <repo-url> PhotoSorting
cd PhotoSorting

# 安装依赖
uv sync

# 准备地理数据（首次使用）
uv run python prepare_geo_data.py
```

### 使用

**交互模式**（默认）：

```bash
uv run photosorting
# 按提示输入源文件夹、目标文件夹等
```

**命令行模式**（适合脚本/批量处理）：

```bash
# 基本用法
uv run photosorting --source ./Sample --output ./Output

# Dry-Run 试运行
uv run photosorting -s ./Sample -n

# 使用 GCJ-02 火星坐标匹配（当你的 GADM 数据是火星坐标时）
uv run photosorting -s ./Sample --china-crs gcj02

# 指定配置文件 + 调试日志
uv run photosorting -s ./Sample -c config.json --log-level DEBUG

# 显示版本
uv run photosorting --version
```

---

## 🗂️ 输出结构

```
Output/
├── 2025-10·深圳/
│   ├── 20251001_143025.jpg
│   ├── 20251001_143025.mov      ← Live Photo 视频跟随照片
│   └── 20251001_143026.jpg
├── 2025-10·北京/
│   └── 20251003_091200.jpg
├── Other/2025-10/                ← 无 GPS 但有日期
│   └── 20251005_120000.png
└── Unknown/                      ← 无日期
    └── DSC_0001.jpg
```

---

## ⚙️ 配置

通过 `config.json` 自定义（也可以从命令行覆盖）：

```json
{
  "china_crs": "wgs84",
  "dry_run": false,
  "max_scan_workers": 8,
  "image_extensions": [".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".dng", ".bmp", ".gif", ".tiff", ".tif"],
  "video_extensions": [".mov", ".mp4", ".3gp", ".m4v"]
}
```

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `china_crs` | GADM 中国数据的坐标系：`wgs84` 或 `gcj02` | `wgs84` |
| `dry_run` | 是否仅分析不移动 | `false` |
| `max_scan_workers` | 并发扫描线程数 | `8` |

---

## 🗺️ GCJ-02 火星坐标说明

照片 GPS 标签存储的是 **WGS-84** 坐标。工具默认假设中国城市边界数据（GADM）也是 WGS-84，会直接匹配。

如果你的 GADM 数据是 **GCJ-02**（火星坐标），有两种处理方式：

**方式一**：通过命令行指定（推荐）
```bash
uv run photosorting -s ./photos --china-crs gcj02
```

**方式二**：在配置文件中设置
```json
{ "china_crs": "gcj02" }
```

这样工具会自动将照片 WGS-84 坐标转换为 GCJ-02 后再查找城市。

---

## 📦 Nuitka 打包

支持编译为独立可执行文件分发：

```bash
# 安装构建依赖
uv sync --group dev

# 编译为独立文件夹（推荐：启动更快）
uv run python build_nuitka.py

# 编译为单个 .exe 文件
uv run python build_nuitka.py --onefile
```

> **注意**：DuckDB 含原生扩展，若 `--onefile` 模式出现 DLL 加载问题，请用 `--onefolder` 模式或回退 PyInstaller：
> ```bash
> uvx pyinstaller --onefile --add-data "data;data" src/photosorting/cli.py
> ```

---

## 🏗️ 技术架构

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| 包管理 | uv |
| EXIF | Pillow + pillow-heif |
| 视频元数据 | ffprobe / exiftool (自动检测) |
| 地理查询 | DuckDB + Spatial 扩展 |
| 地理数据 | Natural Earth + GADM (GeoPackage) |
| TUI | Rich |
| 打包 | Nuitka |
| 坐标系 | WGS-84 ↔ GCJ-02 双向转换 |

---

## 📁 项目结构

```
PhotoSorting/
├── src/photosorting/      # 核心代码
│   ├── cli.py             # CLI 入口 (交互 + 命令行)
│   ├── config.py          # 配置管理
│   ├── metadata.py        # 元数据提取 (照片/视频)
│   ├── scanner.py         # 文件扫描 + 并发
│   ├── geo_resolver.py    # DuckDB 地理匹配
│   ├── gps_utils.py       # WGS-84 ↔ GCJ-02 转换
│   └── mover.py           # 文件归类移动
├── data/                  # 地理边界数据 (GeoPackage)
├── docs/                  # 设计文档 & ADR
├── Sample_105APPLE/       # 测试样本
├── build_nuitka.py        # Nuitka 打包脚本
├── prepare_geo_data.py    # 地理数据下载脚本
└── pyproject.toml         # 项目配置
```

---

## 📄 License

MIT