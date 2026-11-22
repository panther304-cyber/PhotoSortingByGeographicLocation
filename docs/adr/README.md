# Architecture Decision Records — PhotoSorting

## ADR-001: Python 作为开发语言

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
使用 **Python 3.12+** 作为开发语言。

### 理由
- DuckDB 有一流的 Python 绑定，支持内嵌模式和 Spatial 扩展
- Pillow 提供完善的 EXIF 读取能力
- Rich 提供优秀的 TUI 进度条和日志展示
- 丰富的生态系统覆盖所有需要的功能
- 开发效率高，迭代快

---

## ADR-002: 视频元数据提取策略

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
**双工具自动检测策略**：优先 `ffprobe`，回退 `exiftool`，均不可用时仅用文件系统时间。

---

## ADR-003: 支持的文件格式

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
全量支持以下格式 + 用户可配置扩展名追加：

| 类别 | 格式 |
|------|------|
| 照片 | `.jpg` `.jpeg` `.heic` `.heif` `.png` `.webp` `.dng` `.bmp` `.gif` `.tiff` `.tif` |
| 视频 | `.mov` `.mp4` `.3gp` `.m4v` |

---

## ADR-004: Live Photo 配对处理

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
同名不同扩展名的文件对以**照片为主源提取元数据**，视频跟随归入同一文件夹。重命名时两者使用相同时间戳前缀。

---

## ADR-005: 坐标系处理 (WGS-84 ↔ GCJ-02)

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
代码中预置 WGS-84 ↔ GCJ-02 双向转换函数，兼容两种坐标系的数据源。配置文件标记数据源坐标系。

---

## ADR-006: 地理边界数据分发策略

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
地理边界数据**打包进软件发布包**，采用 **GeoPackage (.gpkg)** 格式。~50MB 增量可接受。

### GeoPackage 数据结构
- `countries`: NE 110m Admin 0 国家边界 (WGS-84), `name_zh`, `name_en`
---

## ADR-007: DuckDB 空间查询架构

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
**批量收集 + 一次性 Spatial JOIN**：
1. 阶段1: 遍历文件 → 收集所有 GPS + 时间 → 临时内存表
2. 阶段2: DuckDB 一次 Spatial JOIN → 批量返回归属
3. 阶段3: 逐文件移动 → 更新进度条

### SQL 核心查询
```sql
SELECT p.file_path,
  COALESCE(c.city_name, n.name_zh, 'Other') AS location,
  CASE WHEN c.city_name IS NOT NULL THEN 'city'
       WHEN n.name_zh IS NOT NULL THEN 'country'
       ELSE 'unknown' END AS geo_level
FROM photos AS p
LEFT JOIN china_cities AS c ON ST_Contains(c.geom, ST_Point(p.lon, p.lat))
LEFT JOIN ne_countries AS n ON ST_Contains(n.geom, ST_Point(p.lon, p.lat))
  AND c.city_name IS NULL;
```

---

## ADR-008: TUI 框架

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
使用 **Rich** 库，包含：输入框、进度条、信息汇总表格。

```
╔══════════════════════════════════════════╗
║  📸 PhotoSorting - 照片整理工具          ║
╠══════════════════════════════════════════╣
║  源文件夹: [/path/to/source]             ║
║  目标文件夹: [/path/to/output]           ║
║  [开始整理]  [Dry-Run]  [退出]           ║
╠══════════════════════════════════════════╣
║  ⠋ 正在移动文件... 45/105  [████░░] 42% ║
╠══════════════════════════════════════════╣
║  汇总信息 (按月份+地点分组)              ║
╚══════════════════════════════════════════╝
```

---

## ADR-009: 文件命名与日期回退

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
统一重命名为 `YYYYMMDD_HHMMSS[_序号].扩展名`。

日期获取优先级:
1. EXIF DateTimeOriginal / QuickTime CreationDate
2. 文件名日期模式解析
3. 文件修改时间 (mtime)
4. 标记为 "Unknown_YYYYMMDD"

---

## ADR-010: 并发策略

**状态**: 已接受 | **日期**: 2026-10-13

| 阶段 | 策略 | 理由 |
|------|------|------|
| 扫描+元数据 | 多线程并发 | IO-bound |
| 地理匹配 | 单线程 | DuckDB内部已并行 |
| 文件移动 | 单线程顺序 | 避免磁盘争抢 |

---

## ADR-011: 项目工具链

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
**uv** 管理依赖 + **Nuitka** 编译分发。若 Nuitka 不兼容 DuckDB，回退 PyInstaller。

---

## ADR-012: Dry-Run 模式

**状态**: 已接受 | **日期**: 2026-10-13

### 决策
可选 Dry-Run，默认直接执行。Dry-Run 跳过实际文件操作，仅展示分类结果。
- `china_cities`: 中国地级市边界 (可配置坐标系), `city_name`, `province`