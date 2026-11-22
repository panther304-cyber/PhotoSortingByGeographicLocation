# 术语表 (Glossary) — PhotoSorting

## 核心概念

| 术语 | 英文 | 定义 |
|------|------|------|
| **源文件夹** | Source Folder | 用户从手机导出照片到本机的原始文件夹，程序从中读取照片/视频 |
| **目标文件夹** | Output Folder | 整理后照片/视频存放的根目录 |
| **子文件夹** | Sub-folder | 目标文件夹下按 `YYYY-MM·地理位置` 或 `Other/YYYY-MM` 格式命名的一级子目录 |
| **拍摄时间** | Capture Time | 照片/视频被拍摄的时刻，优先取 EXIF DateTimeOriginal，其次是文件名解析、文件 mtime |
| **拍摄地点** | Capture Location | GPS 经纬度对应的地理名称，国内精确到城市，国外精确到国家 |
| **地理位置** | Geo-location | 经过 DuckDB Spatial 空间查询后得到的中文地理名称，用于文件夹命名 |

## 文件相关

| 术语 | 英文 | 定义 |
|------|------|------|
| **媒体文件** | Media File | 符合条件的照片或视频文件 |
| **Live Photo 对** | Live Photo Pair | 同基础名、不同扩展名的一对文件（一张照片 + 一个短视频），作为一个逻辑条目处理 |
| **配对主文件** | Pair Primary | Live Photo 对中的照片文件，其元数据被用作整个对的代表 |
| **配对从文件** | Pair Secondary | Live Photo 对中的视频文件，跟随主文件归类和命名 |
| **重命名策略** | Rename Strategy | 统一将文件重命名为 `YYYYMMDD_HHMMSS[_序号].扩展名` 格式 |
| **文件移动** | File Move | 尝试 rename 操作，失败时（跨盘）回退为 copy + delete |
| **Dry-Run** | Dry-Run | 试运行模式，执行扫描和地理匹配但不实际移动文件，仅展示分类结果 |

## 地理相关

| 术语 | 英文 | 定义 |
|------|------|------|
| **WGS-84** | World Geodetic System 1984 | GPS 使用的全球坐标系 (EPSG:4326)，照片 GPS 标签使用此坐标系 |
| **GCJ-02** | 国测局坐标系 / 火星坐标系 | 中国法律要求的地图坐标加密坐标系，相对于 WGS-84 有 100-700 米偏移 |
| **坐标转换** | Coordinate Transformation | WGS-84 ↔ GCJ-02 之间的数学转换，用于兼容不同数据源 |
| **GeoPackage** | .gpkg | OGC 标准的单文件地理数据库格式，用于存储国家和城市边界多边形 |
| **空间索引** | Spatial Index (R-tree) | DuckDB 为加速 `ST_Contains` 查询而自动构建的索引结构 |
| **ST_Contains** | Spatial Contains | 空间包含判定函数：判断一个点（经纬度）是否在一个多边形（国家/城市边界）内部 |
| **边界数据** | Boundary Data | Natural Earth 110m 国家边界 + 中国地级市边界多边形数据 |
| **颗粒度** | Granularity | 中国国内精确到城市级别，国外精确到国家级别 |

## 文件夹命名

| 术语 | 英文 | 定义 |
|------|------|------|
| **位置文件夹** | Location Folder | `YYYY-MM·地理位置` 格式，如 `2024-10·上海`、`2024-10·日本` |
| **Other 文件夹** | Other Folder | 无 GPS 信息照片的归宿，`Other/YYYY-MM` 格式，如 `Other/2024-10` |
| **Unknown** | Unknown Date | 连拍摄时间都无法确定的文件，单独分类为 `Unknown` |

## 技术组件

| 术语 | 英文 | 定义 |
|------|------|------|
| **DuckDB** | DuckDB | 嵌入式列式分析数据库，用于执行空间查询 |
| **Spatial Extension** | DuckDB Spatial | DuckDB 的空间扩展，提供 `ST_Contains`、`ST_Point` 等 GIS 函数 |
| **Rich** | Rich | Python TUI 库，提供进度条、表格、面板等终端 UI 组件 |
| **Pillow** | Pillow (PIL) | Python 图像处理库，用于读取照片 EXIF 元数据 |
| **ffprobe** | FFprobe | FFmpeg 工具集的媒体信息提取工具 |
| **exiftool** | ExifTool | Phil Harvey 的通用元数据提取工具，支持几乎所有媒体格式 |