# ArcGIS Pro 模板制作指南

本文档说明如何制作 `location_map_template.aprx`，以及各元素的命名规范。

## 1. 为什么需要模板

`_arcgis_worker.py` 优先使用预制模板（模板法），其次才用全代码创建（fallback）。

- **模板法**：打开 `.aprx` → 修改数据源/文字 → 导出，布局精确、代码简单。
- **全代码法**：通过 arcpy.mp API 从代码创建布局，灵活但样式调整繁琐。

---

## 2. 模板存放位置

```
src/resources/templates/
├── location_map_template.aprx   ← 主模板（完整三图框布局）
└── blank_seed.aprx              ← 空白种子（仅在 MEMORYLOCATION 不可用时使用）
```

---

## 3. 制作步骤

### 3.1 新建项目

1. 打开 ArcGIS Pro → **New Project** → 选择 **Blank** 模板
2. 保存路径：任意临时位置（最终会复制到 `src/resources/templates/`）

### 3.2 创建三个地图

在 **Catalog Pane → Maps** 中新建三个 Map，**名称必须完全一致**：

| 名称 | 用途 | 建议投影 |
|------|------|---------|
| `China_Map` | 中国全图 | Lambert Conformal Conic (EPSG:4490 + proj) |
| `Province_Map` | 省级地图 | WGS 84 (EPSG:4326) |
| `City_Map` | 研究区详图 | WGS 84 或 UTM |

### 3.3 创建布局

1. **Insert → New Layout → A4 Landscape (297×210mm)**
2. 将布局重命名为 `LocationMap`（右键 Layout → Properties → Name）

### 3.4 添加地图框

按照 SPEC §4.2 的尺寸添加三个 Map Frame（单位：mm，坐标原点为页面左下角）：

| Map Frame 名称 | 关联 Map | X（左） | Y（下） | 宽 | 高 |
|---------------|---------|--------|--------|----|----|
| `China_MapFrame` | `China_Map` | 5 | 127 | 90 | 78 |
| `Province_MapFrame` | `Province_Map` | 5 | 22 | 90 | 62 |
| `City_MapFrame` | `City_Map` | 100 | 22 | 182 | 155 |

操作方法：
1. 在 Layout 视图中，**Insert → Map Frame** → 选择对应 Map
2. 在 **Format → Size & Position** 中输入精确坐标和尺寸
3. 在 **Properties → General → Name** 中设置名称

### 3.5 添加经纬网

在 `City_MapFrame` 上右键 → **Properties → Grids → Add Graticule**，初始间距设为 0.5°（worker 脚本会通过 CIM 动态调整）。

### 3.6 添加装饰元素

在 Layout 视图中添加以下元素，**名称必须完全一致**：

| 元素类型 | 名称 | 位置/大小 (mm) | 说明 |
|---------|------|--------------|------|
| Text | `Title` | X=100, Y=181, W=182, H=22 | 地图标题，16pt 黑体 |
| Text | `Subtitle` | X=100, Y=177, W=182, H=6 | 副标题（可选），9pt |
| Text | `DataSource` | X=5, Y=5, W=287, H=8 | 底部信息栏，8pt |
| North Arrow | `NorthArrow` | X=253, Y=155, W=15, H=20 | 指北针，右上角 |
| Scale Bar | `ScaleBar` | X=102, Y=24, W=60, H=8 | 比例尺，左下角 |
| Legend | `Legend` | X=243, Y=25, W=38, H=40 | 图例，右下角 |

添加文字元素：**Insert → Text** → 双击设置文字 → **Properties → Name** 设置名称

添加指北针：**Insert → North Arrow** → 选择样式 → 设置 Name

添加比例尺：**Insert → Scale Bar** → 选择样式 → 关联到 `City_MapFrame` → 设置 Name

### 3.7 保存并复制模板

1. **File → Save** 保存项目
2. 将 `.aprx` 文件复制到 `src/resources/templates/location_map_template.aprx`
3. Git 提交该文件（约 5–10 MB）

---

## 4. 元素命名速查表

worker 脚本通过以下名称查找元素，**区分大小写，必须完全一致**：

```
Maps:
  China_Map
  Province_Map
  City_Map

Layout:
  LocationMap

Map Frames:
  China_MapFrame
  Province_MapFrame
  City_MapFrame

Text Elements:
  Title
  Subtitle
  DataSource

Surround Elements:
  NorthArrow
  ScaleBar
  Legend
```

---

## 5. 空白种子 `.aprx` 制作

当模板文件不存在时，worker 尝试使用 `blank_seed.aprx`（用于全代码路径）：

1. 新建空白 ArcGIS Pro 项目，不添加任何内容
2. **File → Save**
3. 复制到 `src/resources/templates/blank_seed.aprx`

> 注意：ArcGIS Pro 3.3+ 支持 `"MEMORYLOCATION"` 关键字，可跳过此步骤。

---

## 6. 版本要求

| 功能 | 最低版本 |
|------|---------|
| 独立脚本运行 | ArcGIS Pro 2.0+ |
| `createLayout` / `createMapFrame` | ArcGIS Pro 3.2+ |
| `CreateExportFormat` + `layout.export()` | ArcGIS Pro 3.4+ |
| `MEMORYLOCATION` 关键字 | ArcGIS Pro 3.3+ |
| CIM Access (`getDefinition` / `setDefinition`) | ArcGIS Pro 2.5+ |

---

## 7. 常见问题

**Q: worker 提示"未找到 LocationMap"**
A: 检查 Layout 名称是否正确设为 `LocationMap`（区分大小写）。

**Q: 地图框位置不对**
A: 在 ArcGIS Pro 中，Format → Size & Position 对话框以 **页面左下角为原点**，单位 mm，与本指南一致。

**Q: 导出时中文乱码**
A: 确保 worker 脚本以 UTF-8 编码运行，ArcGIS Pro 的 Python 环境已自动处理，但项目文件路径中避免特殊字符。

**Q: 模板太大，不想进 Git**
A: 可以用 Git LFS 管理 `.aprx` 文件，或在 README 中说明手动下载位置。
