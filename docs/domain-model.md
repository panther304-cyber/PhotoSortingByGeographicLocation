# 领域模型 (Domain Model) — PhotoSorting

## 实体关系图

```
┌─────────────┐       包含       ┌─────────────┐
│  SourceDir  │─────────────────▶│  MediaFile   │
│  (源文件夹)  │     1..*        │  (媒体文件)   │
└─────────────┘                  └──────┬──────┘
                                        │
                                   ┌────┴────┐
                              LivePhoto?   单独文件
                                   │          │
                          ┌────────▼──┐  ┌───▼────┐
                          │LivePhotoPair│  │SingleFile│
                          │ (LivePhoto对)│  │(单独文件) │
                          └─────┬──────┘  └───┬────┘
                                │             │
                                └──────┬──────┘
                                       │ 提取元数据
                                ┌──────▼──────┐
                                │  MediaMeta   │
                                │  (元数据)     │
                                ├──────────────┤
                                │ + capture_time│
                                │ + latitude    │
                                │ + longitude   │
                                │ + file_path   │
                                │ + file_size   │
                                │ + media_type  │
                                └──────┬──────┘
                                       │
                          ┌────────────┼────────────┐
                          │            │            │
                    有GPS+有日期   有日期无GPS   无日期无GPS
                          │            │            │
                   ┌──────▼──┐  ┌─────▼───┐  ┌────▼────┐
                   │GeoQuery │  │ Other   │  │Unknown  │
                   │(地理查询)│  │(Other夹)│  │(未知)   │
                   └──────┬──┘  └─────┬───┘  └────┬────┘
                          │            │            │
                   ┌──────▼──┐  ┌─────▼───┐  ┌────▼────┐
                   │中国城市? │  │YYYY-MM  │  │Unknown  │
                   │或国家名  │  │         │  │         │
                   └──────┬──┘  └─────┬───┘  └────┬────┘
                          │            │            │
                          └────────────┼────────────┘
                                       │
                                ┌──────▼──────┐
                                │ TargetPath  │
                                │ (目标路径)   │
                                ├──────────────┤
                                │ + folder_name│
                                │ + new_filename│
                                └──────┬──────┘
                                       │
                                ┌──────▼──────┐
                                │ FileOperation│
                                │ (文件操作)   │
                                ├──────────────┤
                                │ + move/copy  │
                                │ + result     │
                                └──────────────┘
```

## 核心实体

### MediaFile（媒体文件）
- `path`: 文件的绝对路径
- `basename`: 基础文件名（不含扩展名），用于 Live Photo 配对
- `extension`: 扩展名（小写，含点号）
- `is_video`: 是否为视频文件
- `file_size`: 文件大小（字节）

### MediaMeta（元数据）
- `capture_time`: 拍摄时间 (datetime)
- `capture_time_source`: 时间来源 (exif / filename / mtime / unknown)
- `latitude`: 纬度 (WGS-84, 可为 None)
- `longitude`: 经度 (WGS-84, 可为 None)
- `has_gps`: 是否有 GPS 坐标

### GeoLocation（地理位置归属）
- `name_zh`: 中文地理名称（城市名或国家名）
- `level`: 归属级别 (city / country / other / unknown)
- `province`: 所属省份（仅 city 级别）

### TargetPath（目标路径）
- `folder_name`: 子文件夹名，格式：
  - `YYYY-MM·{地理位置}` （有 GPS）
  - `Other/YYYY-MM` （无 GPS 有日期）
  - `Unknown` （无日期）
- `new_filename`: 新文件名 `YYYYMMDD_HHMMSS[_序号].扩展名`

### FileOperation（文件操作结果）
- `source`: 源路径
- `target`: 目标完整路径
- `operation`: 操作类型 (move / copy / copy_fallback)
- `success`: 是否成功
- `error`: 错误信息（如有）

## 处理流水线

```
SourceDir
  │
  ├─[阶段1: 文件扫描]─────────────────────────
  │  遍历源文件夹 → 过滤支持的扩展名 →
  │  检测 Live Photo 配对 → 生成 MediaFile 列表
  │
  ├─[阶段1.5: 元数据提取]─────────────────────
  │  对每个 MediaFile：
  │    照片 → Pillow EXIF
  │    视频 → ffprobe/exiftool (或跳过 Live Photo 从文件)
  │  构建 MediaMeta 列表
  │
  ├─[阶段2: 地理匹配]─────────────────────────
  │  收集有 GPS 的 MediaMeta →
  │  DuckDB 加载 GeoPackage →
  │  执行 Spatial JOIN →
  │  映射回 GeoLocation
  │
  ├─[阶段3: 目标路径计算]──────────────────────
  │  MediaMeta + GeoLocation →
  │  计算 folder_name + new_filename →
  │  生成 TargetPath 列表
  │
  ├─[阶段4: 文件操作]─────────────────────────
  │  Dry-Run? → 仅打印日志
  │  否则 → 创建目标文件夹 →
  │    尝试 os.rename (同盘移动) →
  │    失败 → shutil.copy2 + os.remove (跨盘/权限)
  │
  └─[阶段5: 汇总报告]─────────────────────────
     按 folder_name 分组统计 →
     Rich Table 展示结果
```