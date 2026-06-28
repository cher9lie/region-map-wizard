# 研究区区位图自动制图工具 — 技术规格书

> **项目名称**: Region Map Wizard (rmw)
> **版本**: v1.0.0-alpha
> **许可证**: GPL-3.0 (与 QGIS 许可兼容)
> **最后更新**: 2026-06-26

---

## 1. 产品定义

### 1.1 一句话描述

选中国省市或上传 SHP → 一键从 GEE 下载 DEM/影像 → 自动生成科研论文级三级区位图（国→省→市），支持 QGIS / ArcGIS Pro / Cartopy 三种渲染引擎。

### 1.2 用户画像

| 画像 | 描述 | 典型场景 |
|------|------|---------|
| 地学研究生 | 需要在论文中放研究区区位图，不精通 GIS 制图 | 毕业论文配图 |
| 科研人员 | 批量制作不同城市的区位图用于对比研究 | 期刊投稿 |
| GIS 从业者 | 需要快速出图，不想每次手动排版 | 项目报告 |

### 1.3 竞品对标

| 功能 | 商业原工具 | Study Area Map Generator | **本项目目标** |
|------|----------|--------------------------|-------------|
| 研究区选择 | 中国省市 | 全球国家级 | 中国省市 + 自定义 SHP |
| GEE 数据集成 | ✅ | ❌ | ✅ |
| 三级区位图 | ✅ (国/省/市) | ❌ (仅国家+inset) | ✅ (国/省/市) |
| DEM 高程设色 | ✅ | ❌ | ✅ |
| 山体阴影 | ✅ | ❌ | ✅ |
| Sentinel-2 | ✅ | ❌ | ✅ |
| 出图引擎 | ArcGIS Pro | Cartopy | QGIS / ArcGIS / Cartopy |
| 自定义 SHP | ❌ → 新增 | ❌ | ✅ |
| 费用 | 收费 + ArcGIS授权 | 免费 | 免费 |
| 开源 | ❌ | ✅ | ✅ |

---

## 2. 系统架构

### 2.1 模块依赖图

```
main.py (入口)
  └── gui/
       ├── main_window.py ──────────┐
       ├── gee_auth_dialog.py       │ UI 事件
       └── widgets.py               │
            │                       ▼
            │              core/pipeline.py (主调度)
            │               ├── core/gee_fetcher.py      ← earthengine-api, geemap
            │               ├── core/data_processor.py    ← rasterio, geopandas
            │               ├── core/boundary_manager.py  ← geopandas
            │               └── core/cache_manager.py     ← pathlib, hashlib
            │                       │
            │                       ▼
            │              renderers/base.py (ABC)
            │               ├── renderers/qgis_renderer.py     ← PyQGIS
            │               ├── renderers/arcgis_renderer.py   ← arcpy (subprocess)
            │               └── renderers/cartopy_renderer.py  ← cartopy, matplotlib
            │
            └── data/
                 ├── china_admin.gpkg        (内置行政边界)
                 ├── cities.json             (省市层级索引)
                 └── color_ramps.json        (色带定义)
```

### 2.2 进程模型

```
┌─ 主进程 (PyQt5 GUI, 主线程) ─────────────────────────────┐
│  事件循环、UI 渲染、用户交互                                │
│                                                          │
│  ┌─ QThread: MapWorker ─────────────────────────────┐    │
│  │  GEE 下载 → 数据处理 → 渲染引擎调用               │    │
│  │  通过 pyqtSignal 向主线程汇报进度                  │    │
│  └───────────────────────────────────────────────────┘    │
│                                                          │
│  (ArcGIS Pro 模式: 通过 subprocess.Popen 调用外部 Python) │
└──────────────────────────────────────────────────────────┘
```

---

## 3. 数据规格

### 3.1 行政边界数据 — china_admin.gpkg

**格式**: OGC GeoPackage (单文件 SQLite 数据库)
**坐标系**: EPSG:4326 (WGS 84)
**数据来源**: 天地图官方行政区划数据 GS(2024)0650 + 九段线

**图层定义**:

| 图层名 | 几何类型 | 字段 | 说明 |
|--------|---------|------|------|
| `country` | MultiPolygon | `name`, `name_en` | 中国国界（含南海诸岛） |
| `province` | MultiPolygon | `adcode` (CHAR 6), `name`, `name_en`, `center_lon`, `center_lat` | 34个省级单位 |
| `city` | MultiPolygon | `adcode` (CHAR 6), `province_adcode` (CHAR 6), `name`, `name_en`, `center_lon`, `center_lat` | 约340个地级市 |
| `nine_dash_line` | MultiLineString | `name` | 南海九段线 |

**数据质量要求**:
- 拓扑无缝: 省界之间无间隙无重叠
- 坐标精度: 小数点后至少 5 位
- 完整性: 包含港澳台、南海诸岛

### 3.2 省市索引 — cities.json

```jsonc
{
  "version": "2024.1",
  "data_source": "天地图 GS(2024)0650",
  "provinces": [
    {
      "adcode": "110000",
      "name": "北京市",
      "name_en": "Beijing",
      "center": [116.4074, 39.9042],
      "cities": [
        {
          "adcode": "110100",
          "name": "北京市",
          "name_en": "Beijing",
          "center": [116.4074, 39.9042]
        }
      ]
    },
    {
      "adcode": "130000",
      "name": "河北省",
      "name_en": "Hebei",
      "center": [114.5149, 38.0428],
      "cities": [
        {
          "adcode": "130100",
          "name": "石家庄市",
          "name_en": "Shijiazhuang",
          "center": [114.5149, 38.0428]
        },
        {
          "adcode": "130200",
          "name": "唐山市",
          "name_en": "Tangshan",
          "center": [118.1802, 39.6305]
        }
        // ... 更多城市
      ]
    }
    // ... 全部34个省份
  ]
}
```

### 3.3 色带定义 — color_ramps.json

```jsonc
{
  "dem_hypsometric": {
    "description": "DEM 经典分层设色",
    "unit": "meters",
    "stops": [
      {"value": -200, "color": "#2b83ba", "label": "≤0"},
      {"value": 0,    "color": "#abdda4", "label": "0"},
      {"value": 200,  "color": "#ffffbf", "label": "200"},
      {"value": 500,  "color": "#fdae61", "label": "500"},
      {"value": 1000, "color": "#d7191c", "label": "1000"},
      {"value": 2000, "color": "#a6611a", "label": "2000"},
      {"value": 3500, "color": "#dfc27d", "label": "3500"},
      {"value": 5000, "color": "#f5f5f5", "label": "5000"},
      {"value": 8848, "color": "#ffffff", "label": ">5000"}
    ]
  },
  "dem_green_brown": {
    "description": "绿色→棕色 地形设色",
    "unit": "meters",
    "stops": [
      {"value": 0,    "color": "#1a9641"},
      {"value": 300,  "color": "#a6d96a"},
      {"value": 800,  "color": "#ffffbf"},
      {"value": 1500, "color": "#fdae61"},
      {"value": 3000, "color": "#d73027"},
      {"value": 5000, "color": "#ffffff"}
    ]
  }
}
```

### 3.4 GEE 数据源参数

| 数据类型 | GEE Asset ID | 分辨率 | 波段 | 下载参数 |
|---------|-------------|--------|------|---------|
| SRTM DEM | `USGS/SRTMGL1_003` | 30m | `elevation` | scale=30, crs=EPSG:4326 |
| 山体阴影 | 运算生成: `ee.Terrain.hillshade(dem)` | 30m | 单波段 | scale=30, crs=EPSG:4326 |
| Sentinel-2 真彩色 | `COPERNICUS/S2_SR_HARMONIZED` | 10m | B4,B3,B2 | scale=10, crs=EPSG:4326, 去云 median 合成 |

**Sentinel-2 预处理流程**:
```
1. 时间筛选: 默认最近12个月, 用户可指定
2. 云量过滤: CLOUDY_PIXEL_PERCENTAGE < 20 (可配置)
3. 去云合成: .median()
4. 波段选择: B4 (Red, 665nm), B3 (Green, 560nm), B2 (Blue, 490nm)
5. 值域缩放: 除以 10000 后 clamp 到 [0, 0.3] (用于可视化)
```

**下载分片策略**:
```
1. 计算研究区 bbox
2. 若 bbox 面积 > 阈值 (默认 40000 km²): 生成 fishnet 网格
   - 网格大小: 自适应, 确保每个 tile < 10 million 像素
3. 每个 tile 独立下载: geemap.download_ee_image() 或 getDownloadURL
4. rasterio.merge.merge() 拼接
5. 按行政区 polygon 裁剪 (rasterio.mask.mask)
6. 写入缓存
```

### 3.5 缓存规则

**缓存目录**: `~/.rmw_cache/` (跨项目共享) 或 `<output_dir>/.cache/` (项目本地)

**缓存 key 计算**:
```python
cache_key = hashlib.sha256(
    f"{adcode}_{data_type}_{scale}_{year if sentinel else 'static'}"
    .encode()
).hexdigest()[:16]

# 示例文件名: ~/.rmw_cache/dem/110100_a3b4c5d6e7f8.tif
```

**缓存失效**:
- DEM / Hillshade: 永不失效 (SRTM 是静态数据)
- Sentinel-2: 按年份缓存, 不同年份独立

---

## 4. 渲染引擎接口规格

### 4.1 抽象基类

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class RenderConfig:
    """渲染配置参数"""
    # === 边界数据 ===
    country_boundary: Path          # 国界 GeoJSON/GPKG
    province_boundary: Path         # 省级边界
    city_boundary: Path             # 市级边界
    province_name: str              # 省份名称 (标注用)
    city_name: str                  # 城市名称 (标注用)
    
    # === 栅格数据 ===
    raster_path: Optional[Path]     # GEE下载的GeoTIFF (None=纯矢量图)
    data_type: str                  # 'dem' | 'hillshade' | 'sentinel2'
    color_ramp: str                 # 色带名称 (引用 color_ramps.json)
    
    # === 输出设置 ===
    output_path: Path               # 输出文件路径
    output_format: str              # 'jpg' | 'png' | 'pdf' | 'tiff' | 'svg'
    dpi: int = 300                  # 输出分辨率
    page_size: str = 'a4_landscape' # 'a4_landscape' | 'a4_portrait' | 'a3_landscape'
    language: str = 'zh'            # 'zh' | 'en'
    
    # === 样式参数 ===
    title: Optional[str] = None     # 自定义标题 (None=自动生成)
    show_grid: bool = True          # 是否显示经纬网
    show_scalebar: bool = True      # 是否显示比例尺
    show_north_arrow: bool = True   # 是否显示指北针
    show_legend: bool = True        # 是否显示图例
    highlight_color: str = '#FF0000' # 研究区高亮边框颜色
    highlight_width: float = 1.5    # 研究区高亮边框宽度 (mm)
    
    # === 自定义 SHP 模式 ===
    custom_shp: Optional[Path] = None  # 用户上传的 SHP
    custom_name: Optional[str] = None  # 自定义区域名称


class BaseRenderer(ABC):
    """渲染引擎抽象基类"""
    
    @abstractmethod
    def check_available(self) -> tuple[bool, str]:
        """检查引擎是否可用
        Returns: (可用, 原因/版本信息)
        """
        pass
    
    @abstractmethod
    def render(self, config: RenderConfig, 
               progress_callback=None) -> Path:
        """执行渲染
        Args:
            config: 渲染配置
            progress_callback: 可选回调 fn(percent: int, message: str)
        Returns: 输出文件路径
        Raises: RenderError
        """
        pass
    
    @abstractmethod
    def get_project_path(self) -> Optional[Path]:
        """返回可编辑的工程文件路径 (.qgz / .aprx)
        若引擎不支持则返回 None
        """
        pass
```

### 4.2 三级区位图排版规格

**页面**: A4 横版 297×210 mm

```
┌─────────────────────────────────────────────────────────────┐
│ 左 margin 5mm                                 右 margin 5mm │
│ ┌─────────────┬───────────────────────────────────────────┐ │
│ │             │              地图标题                      │ │
│ │  (a) 中国    │    (标题栏高度 12mm, 居中, 16pt 黑体)      │ │
│ │  全图        ├───────────────────────────────────────────┤ │
│ │             │                                           │ │
│ │  90×78mm    │         (c) 研究区详图                     │ │
│ │  LambertCC  │                                           │ │
│ │  105°E      │         叠加 GEE 遥感/DEM 数据             │ │
│ │             │         经纬网 (0.5° 或自适应间距)          │ │
│ │  省份红色    │         比例尺 (左下)                      │ │
│ │  高亮填充    │         指北针 (右上)                      │ │
│ │             │         图例 (右下)                        │ │
│ ├─────────────┤                                           │ │
│ │             │         PlateCarree / UTM                 │ │
│ │  (b) 省级   │                                           │ │
│ │  地图        │         约 182×155mm                      │ │
│ │             │                                           │ │
│ │  90×62mm    │                                           │ │
│ │  城市红色    │                                           │ │
│ │  高亮填充    │                                           │ │
│ │             │                                           │ │
│ └─────────────┴───────────────────────────────────────────┘ │
│                                                             │
│  底部信息栏 (8mm): 坐标系、数据来源、制图日期                  │
└─────────────────────────────────────────────────────────────┘
```

**各面板投影参数**:

| 面板 | 投影 | 参数 | 说明 |
|------|------|------|------|
| (a) 中国全图 | Lambert Conformal Conic | central_lon=105°, central_lat=35°, std_par=25°/47° | 中国标准制图投影 |
| (b) 省级图 | PlateCarree 或 UTM | 自适应 | 省级范围 |
| (c) 详图 | PlateCarree 或 UTM zone | 按研究区经度自动选择 UTM zone | 详细展示 |

**标注样式**:

| 元素 | 中文字体 | 英文字体 | 字号 | 颜色 |
|------|---------|---------|------|------|
| 地图标题 | 黑体/SimHei | Arial Bold | 16pt | #333333 |
| 面板标签 (a)(b)(c) | 黑体 | Arial Bold | 12pt | #000000 |
| 经纬网标注 | 宋体/SimSun | Arial | 8pt | #666666 |
| 省份名称 | 宋体 | Arial | 9pt | #333333 |
| 图例文字 | 宋体 | Arial | 8pt | #333333 |
| 比例尺文字 | 宋体 | Arial | 7pt | #333333 |
| 底部信息 | 宋体 | Arial | 7pt | #999999 |

**比例尺规则**:
- 类型: Single Box 或 Double Box
- 自适应分段: 根据地图范围自动计算整数比例尺 (如 0-50-100 km)
- 位置: 详图左下角

**经纬网间距自适应**:
```python
def calc_grid_interval(extent_degrees: float) -> float:
    """根据地图范围自动计算经纬网间距"""
    if extent_degrees > 30: return 10.0
    if extent_degrees > 10: return 5.0
    if extent_degrees > 5:  return 2.0
    if extent_degrees > 2:  return 1.0
    if extent_degrees > 1:  return 0.5
    if extent_degrees > 0.5: return 0.25
    return 0.1
```

### 4.3 ArcGIS Pro 引擎 — 详细设计

#### 4.3.1 环境检测与初始化

```
检测顺序:
1. 环境变量 ARCGIS_PRO_PATH (用户自定义)
2. 注册表 HKLM\SOFTWARE\ESRI\ArcGISPro → InstallDir
3. 常见安装路径:
   - C:\Program Files\ArcGIS\Pro
   - C:\ArcGIS\Pro
4. propy.bat 路径:
   - {InstallDir}\bin\Python\scripts\propy.bat
5. python.exe 路径:
   - {InstallDir}\bin\Python\envs\arcgispro-py3\python.exe

检测方法: subprocess 调用上述 python.exe 执行:
  python -c "import arcpy; print(arcpy.GetInstallInfo()['Version'])"
```

注册表读取示例：
```python
import winreg
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\ESRI\ArcGISPro')
install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
```

#### 4.3.2 进程模型

主进程（PyQt5 GUI）与 arcpy 工作进程之间的通信协议：

```
主进程 (PyQt5, 系统 Python)
  │
  │  1. 将 RenderConfig 序列化为 JSON 临时文件
  │  2. 复制模板 .aprx 到临时目录
  │
  ├─ subprocess.Popen([propy_bat, "_arcgis_worker.py", "--config", config.json])
  │     │
  │     │  _arcgis_worker.py 在 ArcGIS Python 环境中运行:
  │     │    - 读取 config.json
  │     │    - 打开模板 .aprx
  │     │    - 创建/修改地图、布局、数据源
  │     │    - 导出图片
  │     │    - 向 stdout 输出 JSON 进度行:
  │     │      {"step": "loading",  "progress": 10, "message": "加载模板..."}
  │     │      {"step": "data",     "progress": 30, "message": "加载栅格数据..."}
  │     │      {"step": "render",   "progress": 70, "message": "渲染排版..."}
  │     │      {"step": "export",   "progress": 90, "message": "导出 JPG..."}
  │     │      {"step": "done",     "progress": 100, "output": "C:\\output\\map.jpg"}
  │     │    - 异常时输出:
  │     │      {"step": "error", "message": "arcpy 错误详情"}
  │     │
  │  3. 主进程逐行读取 stdout，解析 JSON，更新进度条
  │  4. 子进程结束后，主进程获取输出文件路径
```

#### 4.3.3 模板 .aprx 设计

两种策略对比：

**策略 A（模板法，推荐）**
- 预先在 ArcGIS Pro 中手动制作排版模板 `location_map_template.aprx`
- 包含 3 个 Map：`China_Map` / `Province_Map` / `City_Map`
- 包含 1 个 Layout `LocationMap`（A4 横版 297×210mm）
  - 3 个 MapFrame（位置尺寸与第 4.2 节一致）
  - 预设的指北针、比例尺、图例、标题文本框
- 脚本运行时：复制模板 → 修改数据源 → 调整范围 → 修改文本 → 导出
- 优势：排版美观度有保证、代码简单
- 劣势：模板制作需要 ArcGIS Pro、模板文件约 5–10 MB

**策略 B（全代码创建，ArcGIS Pro ≥ 3.2）**
- 用 `createLayout` + `createMapFrame` + `createMapSurroundElement` 全部从代码创建
- 需要通过 CIM Access 修改经纬网间距、字体等细节属性
- 优势：灵活、无外部模板文件依赖
- 劣势：代码量大、CIM 操作复杂、样式调整困难

**推荐：混合策略**。优先使用预制模板（策略 A），当模板文件缺失时自动 fallback 到全代码创建（策略 B）。模板文件存放于 `src/resources/templates/location_map_template.aprx`。

> **注意**：arcpy.mp 不能凭空创建 .aprx 项目文件（ESRI 官方限制），策略 B 仍需一个空白"种子" .aprx 文件作为基础。

#### 4.3.4 _arcgis_worker.py 完整流程

```python
# _arcgis_worker.py — 在 ArcGIS Pro Python 环境中运行
# 完全独立，不 import 主项目任何模块
import arcpy, json, sys, os, shutil

def report(step, progress, message, **kwargs):
    """向 stdout 输出 JSON 进度（flush 确保主进程实时读取）"""
    print(json.dumps(
        {"step": step, "progress": progress, "message": message, **kwargs},
        ensure_ascii=False
    ), flush=True)

def main(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 1. 复制模板并打开
    report("loading", 5, "打开 ArcGIS Pro 项目模板...")
    work_aprx = os.path.join(config['temp_dir'], 'work.aprx')
    shutil.copy2(config['template_path'], work_aprx)
    aprx = arcpy.mp.ArcGISProject(work_aprx)

    # 2. 获取地图和布局引用
    china_map    = aprx.listMaps('China_Map')[0]
    province_map = aprx.listMaps('Province_Map')[0]
    city_map     = aprx.listMaps('City_Map')[0]
    layout       = aprx.listLayouts('LocationMap')[0]

    # 3. 加载矢量边界
    report("data", 20, "加载行政区边界...")
    china_map.addDataFromPath(config['country_boundary'])
    province_map.addDataFromPath(config['province_boundary'])
    city_map.addDataFromPath(config['city_boundary'])

    # 4. 加载栅格数据
    if config.get('raster_path'):
        report("data", 35, "加载栅格数据...")
        city_map.addDataFromPath(config['raster_path'])

    # 5. 符号化
    report("symbolize", 45, "设置符号化...")
    for lyr in city_map.listLayers():
        if lyr.isRasterLayer:
            sym = lyr.symbology
            if config['data_type'] == 'dem':
                sym.updateColorizer('RasterClassifyColorizer')
                # 从 config['color_ramp'] 设置分类色带
            elif config['data_type'] == 'hillshade':
                sym.updateColorizer('RasterStretchColorizer')
            elif config['data_type'] == 'sentinel2':
                sym.updateColorizer('RasterRGBColorizer')
            lyr.symbology = sym

    # 6. 设置各地图框范围
    report("extent", 60, "设置地图范围...")
    city_mf = layout.listElements('MapFrame_Element', 'City_MapFrame')[0]
    city_lyr = city_map.listLayers(config['city_name'])[0]
    ext = city_mf.getLayerExtent(city_lyr, False, True)
    city_mf.camera.setExtent(ext)
    city_mf.camera.scale *= 1.1  # 留边距

    # 7. 更新文本元素
    report("text", 70, "更新标注...")
    title = layout.listElements('TEXT_ELEMENT', 'Title')[0]
    title.text = f"{config['province_name']}{config['city_name']}研究区区位图"

    # 8. 经纬网格（通过 CIM 修改间距）
    report("grid", 80, "设置经纬网...")
    # 见 4.3.5 节 CIM Access 示例

    # 9. 保存工程副本（供用户后续在 ArcGIS Pro 中编辑）
    report("save", 85, "保存 ArcGIS Pro 工程...")
    output_aprx = os.path.join(
        config['output_dir'],
        f"{config['province_name']}_{config['city_name']}_区位图.aprx"
    )
    aprx.saveACopy(output_aprx)

    # 10. 导出图片
    report("export", 90, "导出图片...")
    output_path = os.path.join(
        config['output_dir'],
        f"{config['province_name']}_{config['city_name']}_区位图.{config['format']}"
    )
    fmt_map = {'pdf': 'PDF', 'jpg': 'JPEG', 'jpeg': 'JPEG',
               'png': 'PNG', 'tif': 'TIFF', 'tiff': 'TIFF'}
    fmt_key = fmt_map.get(config['format'].lower(), 'JPEG')
    fmt = arcpy.mp.CreateExportFormat(fmt_key, output_path)
    fmt.resolution = config.get('dpi', 300)
    layout.export(fmt)

    report("done", 100, "完成", output=output_path, project=output_aprx)
    del aprx  # 释放文件锁

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        main(args.config)
    except Exception as e:
        print(json.dumps({"step": "error", "message": str(e)},
                         ensure_ascii=False), flush=True)
        sys.exit(1)
```

#### 4.3.5 arcpy 符号化 API 参考

| 操作 | API | 说明 |
|------|-----|------|
| DEM 分层设色 | `sym.updateColorizer('RasterClassifyColorizer')` | 设置 classBreaks 和色带 |
| DEM 拉伸渲染 | `sym.updateColorizer('RasterStretchColorizer')` | 单波段拉伸（山体阴影用灰度） |
| RGB 真彩色 | `sym.updateColorizer('RasterRGBColorizer')` | Sentinel-2 B4/B3/B2 |
| 矢量填充色 | `lyr.symbology.renderer.symbol.color` | 修改面填充颜色 |
| 矢量边框 | `lyr.symbology.renderer.symbol.outlineColor` | 修改边框颜色和宽度 |
| 图层透明度 | `lyr.transparency = 50` | 0–100，数值越大越透明 |
| 定义查询 | `lyr.definitionQuery = "adcode = '130000'"` | 仅显示特定要素 |

对于 arcpy.mp API 未暴露的属性（如经纬网间距、字体大小），使用 Python CIM Access：

```python
lyt_cim = layout.getDefinition('V3')
for elm in lyt_cim.elements:
    if elm.name == 'City_MapFrame':
        for grid in elm.grids:
            grid.gridLineOrigin.x = 0.5  # 经度间隔（度）
            grid.gridLineOrigin.y = 0.5  # 纬度间隔（度）
layout.setDefinition(lyt_cim)
```

#### 4.3.6 导出格式与参数

ArcGIS Pro 3.4+ 使用 `CreateExportFormat` + `layout.export(fmt)`：

| 格式 | CreateExportFormat 参数 | 关键属性 |
|------|------------------------|---------|
| PDF  | `'PDF'`  | `resolution`, `embedFonts=True`, `imageCompressionQuality`, `georefInfo` |
| JPEG | `'JPEG'` | `resolution`, `jpegQuality`（0–100） |
| PNG  | `'PNG'`  | `resolution` |
| TIFF | `'TIFF'` | `resolution`, `geoTiffTags=True` |
| SVG  | `'SVG'`  | `resolution`, `compressVectorGraphics` |
| BMP  | `'BMP'`  | `resolution` |

> ArcGIS Pro < 3.4 使用旧方法：`layout.exportToPDF()` / `layout.exportToJPEG()` 等。

#### 4.3.7 ArcGIS 引擎优势与限制

**优势**
- 出图质量是三个引擎中最高的（ArcGIS Pro 渲染引擎成熟度最高）
- 丰富的内置样式库（North Arrow、Scale Bar 各有数十种预设）
- 输出可编辑的 .aprx 项目文件，用户可继续在 ArcGIS Pro 中微调
- CIM Access 提供了极深度的自定义能力
- `export()` 方法支持 11 种格式（PDF / JPEG / PNG / BMP / TIFF / SVG / EPS / EMF / GIF / AIX）

**限制**
- 用户必须安装 ArcGIS Pro（商业软件，需授权）
- arcpy 只能在 ArcGIS Pro 的 conda 环境中运行，不能安装到系统 Python
- 通过 subprocess 调用，主进程无法直接 `import arcpy`
- 不能凭空创建 .aprx，需要预制模板文件（或空白种子文件）
- Windows 独占（ArcGIS Pro 不支持 macOS/Linux）

---

## 5. GUI 规格

### 5.1 技术参数

| 参数 | 值 |
|------|-----|
| UI 框架 | PyQt5 (>=5.15) |
| 最小窗口尺寸 | 720 × 580 px |
| 默认窗口尺寸 | 860 × 680 px |
| DPI 感知 | Qt.AA_EnableHighDpiScaling |
| 样式 | 自定义 QSS, 浅色主题 |
| 图标 | SVG 格式, 支持 HiDPI |
| 国际化 | QTranslator, 中/英双语 .ts 文件 |

### 5.2 信号-槽通信

```
MainWindow
  │
  ├─ [信号] start_requested(config: RenderConfig)
  │     └─→ [槽] MapWorker.run()
  │
  ├─ [信号] cancel_requested()
  │     └─→ [槽] MapWorker.cancel()
  │
  MapWorker (QThread)
  │
  ├─ [信号] progress(percent: int, message: str)
  │     └─→ [槽] MainWindow.update_progress()
  │
  ├─ [信号] log(message: str)
  │     └─→ [槽] MainWindow.append_log()
  │
  ├─ [信号] finished(output_path: str)
  │     └─→ [槽] MainWindow.on_finished()
  │
  └─ [信号] error(error_msg: str)
        └─→ [槽] MainWindow.on_error()
```

### 5.3 配置持久化 — config.json

```jsonc
{
  "gee_project_id": "my-gee-project",
  "last_province": "130000",
  "last_city": "130100",
  "last_data_type": "dem",
  "last_renderer": "qgis",
  "last_output_dir": "C:\\Users\\xxx\\Documents\\RegionMaps",
  "output_format": "jpg",
  "dpi": 300,
  "language": "zh",
  "cache_dir": "",            // 空=使用默认 ~/.rmw_cache
  "qgis_prefix_path": "",     // 空=自动检测
  "arcgis_python_path": "",   // 空=自动检测
  "sentinel2_year_range": 1,  // 最近N年
  "sentinel2_cloud_max": 20   // 最大云量%
}
```

---

## 6. 错误处理规格

### 6.1 错误分类

| 错误码 | 类型 | 说明 | 用户提示 |
|--------|------|------|---------|
| E001 | GEE_AUTH_FAILED | GEE 认证失败 | "请先完成 Google Earth Engine 认证" |
| E002 | GEE_DOWNLOAD_FAILED | GEE 下载失败 | "数据下载失败，请检查网络连接和 GEE 项目配置" |
| E003 | GEE_QUOTA_EXCEEDED | GEE 配额超限 | "GEE 计算配额已超限，请稍后重试" |
| E010 | RENDERER_NOT_AVAILABLE | 渲染引擎不可用 | "未检测到 QGIS 安装，请安装 QGIS 或选择其他引擎" |
| E011 | RENDER_FAILED | 渲染过程失败 | "制图过程出错: {detail}" |
| E020 | BOUNDARY_NOT_FOUND | 行政区边界缺失 | "未找到该行政区的边界数据" |
| E021 | INVALID_SHP | SHP 文件无效 | "上传的 SHP 文件无法读取或投影不明" |
| E030 | IO_ERROR | 文件读写错误 | "文件操作失败: {detail}" |
| E031 | CACHE_ERROR | 缓存操作失败 | "缓存目录不可写" |

### 6.2 日志规格

```python
import logging

# 文件日志: ~/.rmw_cache/logs/rmw_YYYYMMDD.log
# 控制台: INFO 级别
# GUI 日志面板: INFO 级别, 带时间戳

LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"
```

---

## 7. 环境与依赖

### 7.1 Python 版本

**最低**: Python 3.10
**推荐**: Python 3.11 (QGIS 3.38 LTR 内置)

### 7.2 核心依赖

```toml
[project]
dependencies = [
    "PyQt5>=5.15",
    "earthengine-api>=1.4",
    "geemap>=0.35",
    "geopandas>=1.0",
    "rasterio>=1.4",
    "shapely>=2.0",
    "numpy>=1.26",
    "Pillow>=10.0",
]

[project.optional-dependencies]
cartopy = ["cartopy>=0.22", "matplotlib>=3.8", "matplotlib-scalebar>=0.8"]
dev = ["pytest>=8.0", "pytest-qt>=4.4", "ruff>=0.6", "pre-commit>=3.8"]
```

### 7.3 外部软件依赖

| 软件 | 版本 | 必需? | 检测方法 |
|------|------|-------|---------|
| QGIS | ≥ 3.34 LTR | QGIS 引擎必需 | 尝试 `from qgis.core import Qgis; Qgis.version()` |
| ArcGIS Pro | ≥ 3.0 | ArcGIS 引擎必需 | subprocess 调用 arcgis python 检测 `import arcpy` |
| Google Chrome / 浏览器 | 任意 | GEE 首次认证 | — |

### 7.4 QGIS 环境检测与初始化

```python
# Windows QGIS 安装路径检测顺序
QGIS_SEARCH_PATHS_WIN = [
    r"C:\Program Files\QGIS 3.40",
    r"C:\Program Files\QGIS 3.38",
    r"C:\Program Files\QGIS 3.34",
    r"C:\OSGeo4W",
    # 也检查注册表: HKLM\SOFTWARE\QGIS
]

# 需要设置的环境变量
QGIS_ENV_VARS = {
    'QGIS_PREFIX_PATH': '{qgis_root}/apps/qgis',
    'PYTHONPATH': '{qgis_root}/apps/qgis/python;{qgis_root}/apps/qgis/python/plugins',
    'PATH': '{qgis_root}/apps/qgis/bin;{qgis_root}/bin;' + os.environ.get('PATH', ''),
}
```

---

## 8. 测试策略

### 8.1 测试分级

| 级别 | 覆盖 | 工具 | CI |
|------|------|------|-----|
| 单元测试 | data_processor, cache_manager, boundary_manager | pytest | ✅ |
| 集成测试 | gee_fetcher (mock GEE), pipeline | pytest + mock | ✅ |
| 渲染测试 | 各引擎出图对比 | pytest + 图像相似度 | 手动 (需 QGIS 环境) |
| E2E 测试 | 完整流程: 选城市→下载→出图 | 手动 | 手动 |

### 8.2 Mock GEE 测试

```python
# tests/conftest.py
@pytest.fixture
def mock_gee(monkeypatch):
    """用本地 GeoTIFF 替代 GEE 下载"""
    def fake_download(image, filename, **kwargs):
        shutil.copy("tests/fixtures/sample_dem.tif", filename)
    monkeypatch.setattr("core.gee_fetcher.geemap.download_ee_image", fake_download)
```

---

## 9. 项目结构

```
region-map-wizard/
├── pyproject.toml                 # 项目元数据与依赖 (PEP 621)
├── README.md                      # 用户文档
├── README_EN.md                   # English README
├── LICENSE                        # GPL-3.0
├── CONTRIBUTING.md                # 贡献指南
├── CHANGELOG.md                   # 变更日志
├── .gitignore
├── .pre-commit-config.yaml        # 代码格式化
│
├── docs/
│   ├── SPEC.md                    # 本文档
│   ├── architecture.md            # 架构说明 (含图)
│   ├── gee_setup_guide.md         # GEE 配置教程
│   └── screenshots/               # UI 截图
│
├── src/
│   ├── __init__.py
│   ├── main.py                    # 入口
│   ├── constants.py               # 全局常量 (版本号、默认值)
│   │
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py         # 主窗口
│   │   ├── gee_auth_dialog.py     # GEE 认证对话框
│   │   ├── shp_import_dialog.py   # SHP 导入对话框
│   │   ├── settings_dialog.py     # 设置对话框
│   │   ├── widgets.py             # 自定义控件 (日志面板等)
│   │   └── worker.py              # QThread 工作线程
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── pipeline.py            # 主流程调度
│   │   ├── gee_fetcher.py         # GEE 数据获取
│   │   ├── data_processor.py      # 栅格处理 (拼接/裁剪)
│   │   ├── boundary_manager.py    # 行政区边界管理
│   │   ├── cache_manager.py       # 缓存管理
│   │   ├── config_manager.py      # 配置文件读写
│   │   └── exceptions.py          # 自定义异常
│   │
│   ├── renderers/
│   │   ├── __init__.py
│   │   ├── base.py                # 抽象基类 + RenderConfig
│   │   ├── qgis_renderer.py       # QGIS PyQGIS 实现
│   │   ├── arcgis_renderer.py     # ArcGIS Pro 实现
│   │   ├── cartopy_renderer.py    # Cartopy 实现
│   │   └── _arcgis_worker.py      # ArcGIS subprocess 脚本
│   │
│   ├── data/
│   │   ├── china_admin.gpkg       # 行政边界
│   │   ├── cities.json            # 省市索引
│   │   └── color_ramps.json       # 色带
│   │
│   └── resources/
│       ├── style.qss              # PyQt5 样式
│       ├── icons/
│       │   ├── app_icon.svg
│       │   └── ...
│       ├── north_arrows/
│       │   ├── arrow_default.svg
│       │   └── ...
│       ├── templates/
│       │   └── location_map_a4.qpt  # QGIS 布局模板
│       └── i18n/
│           ├── zh_CN.ts
│           └── en_US.ts
│
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── sample_dem.tif          # 测试用小 GeoTIFF
│   │   ├── sample_boundary.geojson # 测试用边界
│   │   └── expected_output.png     # 期望输出参考图
│   ├── test_boundary_manager.py
│   ├── test_cache_manager.py
│   ├── test_data_processor.py
│   ├── test_gee_fetcher.py
│   └── test_pipeline.py
│
└── scripts/
    ├── prepare_boundaries.py       # 边界数据预处理脚本
    ├── download_test_data.py       # 下载测试数据
    └── build_exe.py                # PyInstaller 打包 (Cartopy-only 版)
```

---

## 10. 开发路线图

### Phase 1: 核心 MVP (目标: 2周内可跑通)

**里程碑**: 选北京市 + DEM → QGIS引擎出图 → 一张完整区位图 JPG

- [ ] P1.1 数据准备: cities.json + china_admin.gpkg (至少北京/河北测试数据)
- [ ] P1.2 core/boundary_manager.py: 按 adcode 查询边界
- [ ] P1.3 core/gee_fetcher.py: GEE 认证 + DEM 下载 + 缓存
- [ ] P1.4 core/data_processor.py: GeoTIFF 裁剪
- [ ] P1.5 renderers/qgis_renderer.py: 三级区位图 QgsLayout 渲染
- [ ] P1.6 core/pipeline.py: 串联上述模块
- [ ] P1.7 gui/main_window.py: 基础 GUI
- [ ] P1.8 端到端测试

### Phase 2: 功能完善

- [ ] P2.1 全部 34 省市数据补全
- [ ] P2.2 Hillshade + Sentinel-2 数据类型
- [ ] P2.3 自定义 SHP 导入
- [ ] P2.4 PDF / PNG / TIFF 输出格式
- [ ] P2.5 中英文切换
- [ ] P2.6 设置对话框

### Phase 3: 多引擎

- [ ] P3.1 renderers/cartopy_renderer.py
- [ ] P3.2 renderers/arcgis_renderer.py
- [ ] P3.3 Cartopy-only 版 PyInstaller 打包

### Phase 4: 增值

- [ ] P4.1 批量制图
- [ ] P4.2 QGIS 插件版
- [ ] P4.3 更多 GEE 数据源 (NDVI, 土地覆盖, 夜光)
- [ ] P4.4 自动南海诸岛小地图
