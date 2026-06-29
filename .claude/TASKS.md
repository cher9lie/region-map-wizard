# Claude Code 分阶段开发任务提示词

> 以下提示词按顺序使用，每个对应一个独立的开发任务。
> 使用方式：将对应阶段的提示词粘贴给 Claude Code，它会读取 CLAUDE.md 和 SPEC.md 后开始实现。

---

## 任务 0: 项目脚手架

```
阅读 .claude/CLAUDE.md 和 docs/SPEC.md，然后:

1. 创建 pyproject.toml (PEP 621 格式，项目名 region-map-wizard)
2. 创建 src/__init__.py 和 src/constants.py (版本号、默认常量)
3. 创建 src/core/exceptions.py (按 SPEC 中的错误码定义异常类)
4. 创建 src/renderers/base.py (抽象基类 BaseRenderer + RenderConfig dataclass，完全按照 SPEC 第 4.1 节)
5. 创建 .gitignore, .pre-commit-config.yaml
6. 创建 README.md 框架 (项目简介、安装、使用、贡献)

不要创建任何其他文件。确保所有接口定义与 SPEC 完全一致。
```

---

## 任务 1: 行政区边界管理

```
阅读 .claude/CLAUDE.md 和 docs/SPEC.md 第 3.1-3.2 节，然后:

实现 src/core/boundary_manager.py:

class BoundaryManager:
    def __init__(self, gpkg_path: Path):
        """加载 china_admin.gpkg"""
    
    def list_provinces(self) -> list[dict]:
        """返回所有省份 [{adcode, name, name_en}, ...]"""
    
    def list_cities(self, province_adcode: str) -> list[dict]:
        """返回指定省份下的所有城市"""
    
    def get_boundary(self, adcode: str, level: str) -> gpd.GeoDataFrame:
        """获取指定行政区的边界
        level: 'country' | 'province' | 'city'
        """
    
    def get_country_boundary(self) -> gpd.GeoDataFrame:
        """获取中国国界"""
    
    def get_context_boundaries(self, city_adcode: str) -> tuple:
        """获取制图所需的三级边界
        返回: (country_gdf, province_gdf, city_gdf, all_province_gdf)
        all_province_gdf 是全国所有省份边界（用于中国全图底图）
        """
    
    def validate_custom_shp(self, shp_path: Path) -> tuple[bool, str, gpd.GeoDataFrame]:
        """验证用户上传的 SHP 文件
        返回: (有效, 消息, GeoDataFrame)
        检查: 文件可读、有几何、投影可识别（自动转 EPSG:4326）
        """

同时创建 src/data/cities.json，至少包含以下省份的完整城市数据：
- 北京市、天津市、河北省、山东省、广东省
（其他省份用占位结构，后续补充）

编写 tests/test_boundary_manager.py，测试所有方法。
用 geopandas 读取 GeoPackage。如果 china_admin.gpkg 不存在，
创建一个 scripts/prepare_boundaries.py 脚本，说明如何从天地图数据生成该文件。
```

---

## 任务 2: GEE 数据获取

```
阅读 .claude/CLAUDE.md 和 docs/SPEC.md 第 3.3-3.5 节，然后:

实现 src/core/gee_fetcher.py:

class GEEFetcher:
    def __init__(self, project_id: str, cache_dir: Path):
        """初始化 GEE 连接"""
    
    def authenticate(self) -> bool:
        """执行 GEE 认证 (ee.Authenticate + ee.Initialize)
        首次弹浏览器，凭证保存后自动复用
        """
    
    def is_authenticated(self) -> bool:
        """检查是否已认证"""
    
    def fetch_dem(self, geometry: ee.Geometry, output_path: Path,
                  progress_callback=None) -> Path:
        """下载 SRTM DEM"""
    
    def fetch_hillshade(self, geometry: ee.Geometry, output_path: Path,
                        progress_callback=None) -> Path:
        """下载山体阴影 (基于 SRTM 计算)"""
    
    def fetch_sentinel2(self, geometry: ee.Geometry, output_path: Path,
                        year_range: int = 1, cloud_max: int = 20,
                        progress_callback=None) -> Path:
        """下载 Sentinel-2 真彩色合成影像"""
    
    def _download_with_tiles(self, image: ee.Image, geometry: ee.Geometry,
                             output_path: Path, scale: int,
                             progress_callback=None) -> Path:
        """分片下载大区域数据
        1. 判断是否需要分片 (根据 bbox 面积)
        2. 生成 fishnet 网格
        3. 逐 tile 下载
        4. rasterio.merge 拼接
        5. 按 geometry 裁剪
        """

同时实现 src/core/cache_manager.py:

class CacheManager:
    def __init__(self, cache_dir: Path):
    def get_cache_path(self, adcode: str, data_type: str, **kwargs) -> Path:
    def is_cached(self, adcode: str, data_type: str, **kwargs) -> bool:
    def get_cached(self, adcode: str, data_type: str, **kwargs) -> Optional[Path]:
    def clear_cache(self, adcode: str = None):
    def get_cache_size(self) -> int:  # bytes

关键实现细节:
- DEM 下载 scale=90 (30m 对于整城市太大，90m 足够区位图使用，减少下载量)
- Sentinel-2 下载 scale=100 (区位图不需要 10m 全分辨率)
- 使用 geemap.download_ee_image() 作为主下载方法
- 超时设置: 单 tile 下载 120 秒超时
- 重试: 最多 3 次，指数退避

编写 tests/test_gee_fetcher.py (用 mock，不实际调用 GEE)
编写 tests/test_cache_manager.py
```

---

## 任务 3: 栅格数据处理

```
阅读 docs/SPEC.md 第 3.4 节，然后:

实现 src/core/data_processor.py:

class DataProcessor:
    @staticmethod
    def merge_tiles(tile_paths: list[Path], output_path: Path) -> Path:
        """拼接多个 GeoTIFF tiles"""
    
    @staticmethod
    def clip_to_boundary(raster_path: Path, boundary_gdf: gpd.GeoDataFrame,
                         output_path: Path) -> Path:
        """按矢量边界裁剪栅格"""
    
    @staticmethod
    def apply_color_ramp(raster_path: Path, color_ramp: dict) -> np.ndarray:
        """将单波段 DEM 应用色带，返回 RGBA 数组 (用于 Cartopy 渲染)"""
    
    @staticmethod
    def normalize_sentinel2(raster_path: Path, output_path: Path,
                            min_val: float = 0, max_val: float = 3000) -> Path:
        """Sentinel-2 值域归一化到 0-255 uint8"""
    
    @staticmethod
    def get_raster_extent(raster_path: Path) -> tuple[float, float, float, float]:
        """返回 (xmin, ymin, xmax, ymax) in EPSG:4326"""
    
    @staticmethod
    def get_raster_stats(raster_path: Path) -> dict:
        """返回栅格统计信息 {min, max, mean, nodata, crs, shape, resolution}"""

使用 rasterio 实现所有方法。编写完整测试。
测试用的 sample_dem.tif 用 numpy + rasterio 程序化生成一个小的假 DEM。
```

---

## 任务 4: QGIS 渲染引擎（subprocess 架构，与 ArcGIS 一致）

```
架构说明：
与 ArcGIS 引擎相同，QGIS 通过 subprocess 调用。
QGIS 在 Windows 上拥有独立的 Python 环境（OSGeo4W 或独立安装），
不能也不应该在主进程中 import qgis.core。
入口脚本是 python-qgis.bat（相当于 propy.bat）。

### 4.1 重写 src/renderers/qgis_renderer.py

class QGISRenderer(BaseRenderer):

    def __init__(self):
        self._python_qgis_path: Optional[Path] = None
        self._qgis_version: Optional[str] = None
        self._last_project_path: Optional[Path] = None  # 保存的 .qgz 路径

    def check_available(self) -> tuple[bool, str]:
        """检测 QGIS 是否可用

        检测顺序:
        1. 缓存 self._python_qgis_path
        2. 环境变量 QGIS_INSTALL_PATH → {path}/bin/python-qgis.bat
        3. Windows 注册表:
             HKLM\SOFTWARE\QGIS\QGIS3   → InstallPath
             HKLM\SOFTWARE\QGIS\QGIS3-LTR → InstallPath
           （QGIS 独立安装版写注册表，OSGeo4W 版不写）
        4. 常见路径（遍历版本号）:
             C:\Program Files\QGIS 3.{40,38,36,34,32}\bin\python-qgis.bat
             C:\Program Files\QGIS 3.{40,38,36,34,32}\bin\python-qgis-ltr.bat
             C:\OSGeo4W\bin\python-qgis.bat
             C:\OSGeo4W64\bin\python-qgis.bat
        5. 找到后验证:
             python-qgis.bat -c "from qgis.core import Qgis; print(Qgis.version())"
        6. 返回 (True, "QGIS {version}") 或 (False, "未找到 QGIS 安装")
        """

    def _find_python_qgis(self) -> Optional[Path]:
        """查找 python-qgis.bat，按上述顺序"""

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """通过 subprocess 调用 _qgis_worker.py

        流程（与 ArcGIS 完全一致）:
        1. check_available() → 不可用则 raise RendererNotAvailableError
        2. 将 config 序列化为 JSON 临时文件（Path → str）
        3. subprocess.Popen(
               [str(python_qgis_bat), str(_WORKER_SCRIPT), '--config', config_json],
               stdout=subprocess.PIPE, stderr=subprocess.PIPE
           )  ← 不传 text=True，读 bytes，decode utf-8 errors=replace
        4. 逐行解析 stdout JSON:
             {"step": "loading",  "progress": 10, "message": "..."}
             {"step": "data",     "progress": 30, "message": "..."}
             {"step": "render",   "progress": 60, "message": "..."}
             {"step": "export",   "progress": 90, "message": "..."}
             {"step": "done",     "progress": 100, "output": "...", "project": "..."}
             {"step": "error",    "message": "..."}
        5. returncode 非零则读 stderr 报错
        """

    def get_project_path(self) -> Optional[Path]:
        """返回 worker 保存的 .qgz 项目文件路径"""


### 4.2 实现 src/renderers/_qgis_worker.py

这个脚本在 QGIS 的 Python 环境中独立运行，不导入主项目任何模块。
与主进程通过 stdout JSON 行协议通信（同 _arcgis_worker.py）。

关键实现细节：

0. 开头强制 stdout UTF-8（同 _arcgis_worker.py）:
   sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)

1. QgsApplication 独立模式初始化（python-qgis.bat 已设置好所有环境变量）:
   from qgis.core import QgsApplication
   qgs = QgsApplication([], False)
   qgs.initQgis()
   # ... do work ...
   qgs.exitQgis()

2. 布局创建（QgsPrintLayout，A4 横版，SPEC §4.2 精确尺寸）:
   from qgis.core import (
       QgsProject, QgsPrintLayout, QgsLayoutItemMap,
       QgsLayoutSize, QgsLayoutPoint, QgsUnitTypes,
       QgsRectangle, QgsCoordinateReferenceSystem
   )
   project = QgsProject.instance()
   layout = QgsPrintLayout(project)
   layout.initializeDefaults()
   page = layout.pageCollection().pages()[0]
   page.setPageSize(QgsLayoutSize(297, 210, QgsUnitTypes.LayoutMillimeters))

3. 三个地图框（位置与 ArcGIS worker 一致）:
   map_china    → 90×78mm, 左上 (5, 5), LCC 投影
   map_province → 90×62mm, 左下 (5, 88)
   map_detail   → 182×155mm, 右侧 (100, 22)

   map_china    投影: QgsCoordinateReferenceSystem(
       '+proj=lcc +lat_1=25 +lat_2=47 +lat_0=35 +lon_0=105 +datum=WGS84'
   )
   map_province 投影: EPSG:4326
   map_detail   投影: EPSG:4326（或按经度自动选 UTM）

4. 图层加载:
   country_layer  = QgsVectorLayer(country_boundary, "country", "ogr")
   province_layer = QgsVectorLayer(province_boundary, "province", "ogr")
   city_layer     = QgsVectorLayer(city_boundary, "city", "ogr")
   project.addMapLayer(country_layer, False)
   ...
   每个地图框通过 setLayers([...]) 分配不同图层

5. 图层符号化:
   矢量高亮：
     symbol = QgsFillSymbol.createSimple({
         'color': 'rgba(255,0,0,50)',
         'outline_color': '#ff0000',
         'outline_width': '1.5'
     })
     layer.setRenderer(QgsSingleSymbolRenderer(symbol))

   DEM 分层设色:
     shader_fn = QgsColorRampShader()
     shader_fn.setColorRampType(QgsColorRampShader.Interpolated)
     # 加载 color_ramps.json 中的色带 stops
     shader = QgsRasterShader()
     shader.setRasterShaderFunction(shader_fn)
     renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
     layer.setRenderer(renderer)

   Hillshade 灰度:
     renderer = QgsSingleBandGrayRenderer(layer.dataProvider(), 1)
     layer.setRenderer(renderer)

   Sentinel-2 RGB:
     renderer = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
     layer.setRenderer(renderer)

6. 地图框设置各自图层:
   map_china.setLayers([country_layer, province_highlight_layer])
   map_province.setLayers([province_layer, city_highlight_layer])
   map_detail.setLayers([raster_layer, city_layer])

7. 设置显示范围（从图层 extent 自动计算）:
   china_ext = QgsRectangle(-2800000, -1500000, 2800000, 2500000)  # LCC 坐标
   map_china.zoomToExtent(china_ext)
   province_ext = province_layer.extent()
   province_ext.grow(province_ext.width() * 0.1)
   map_province.zoomToExtent(province_ext)
   city_ext = city_layer.extent()
   city_ext.grow(city_ext.width() * 0.15)
   map_detail.zoomToExtent(city_ext)

8. 装饰元素:
   经纬网（detail 面板）:
     grid = QgsLayoutItemMapGrid('graticule', map_detail)
     grid.setIntervalX(interval)  # 自动计算 0.1°~10°
     grid.setIntervalY(interval)
     grid.setAnnotationEnabled(True)
     map_detail.grids().addGrid(grid)

   比例尺:
     scalebar = QgsLayoutItemScaleBar(layout)
     scalebar.setLinkedMap(map_detail)
     scalebar.setUnits(QgsUnitTypes.DistanceKilometers)
     scalebar.setStyle('Single Box')
     scalebar.attemptMove(QgsLayoutPoint(102, 165, QgsUnitTypes.LayoutMillimeters))

   指北针（SVG 图片）:
     pic = QgsLayoutItemPicture(layout)
     pic.setNorthMode(QgsLayoutItemPicture.GridNorth)  # 绑定到 map_detail
     pic.setLinkedMap(map_detail)
     pic.attemptMove(QgsLayoutPoint(268, 26, QgsUnitTypes.LayoutMillimeters))

   标题文字:
     label = QgsLayoutItemLabel(layout)
     label.setText(title_text)
     label.setFont(QFont('SimHei', 16, QFont.Bold))

9. 保存 .qgz 工程（供用户二次编辑）:
   stem = f"{province_name}_{city_name}_区位图"
   project.setFileName(str(Path(output_dir) / f'{stem}.qgz'))
   project.write()

10. 导出:
    exporter = QgsLayoutExporter(layout)
    if fmt in ('jpg', 'jpeg'):
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = dpi
        exporter.exportToImage(output_path, settings)
    elif fmt == 'pdf':
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = dpi
        exporter.exportToPdf(output_path, settings)
    ...

11. 输出 done JSON:
    _report('done', 100, '完成', output=output_path, project=project_path)

12. qgs.exitQgis() 释放资源


### 4.3 编写测试 tests/test_qgis_renderer.py

全部 mock，不依赖 QGIS 安装：

- test_check_available_no_qgis:
    mock _find_python_qgis 返回 None
    断言返回 (False, ...) 且 reason 含 "未找到"

- test_check_available_with_qgis:
    mock subprocess.run stdout=b"3.40.0\n" returncode=0
    断言返回 (True, "QGIS 3.40.0")

- test_render_calls_popen_with_python_qgis_and_worker:
    mock Popen, stdout 输出 done JSON bytes
    断言 Popen 第一个参数是 [str(python_qgis_bat), str(worker_script), '--config', ...]

- test_render_parses_progress_callbacks:
    mock stdout 输出 loading/data/render/export/done 5 行 JSON bytes
    断言 progress_callback 被调用正确次数，pct 序列正确

- test_render_raises_on_error_step:
    mock stdout 输出 {"step":"error","message":"qgis 崩溃"}
    断言 raise RenderFailedError 且消息含 "qgis 崩溃"

- test_render_unavailable_raises:
    mock check_available 返回 (False, ...)
    断言 raise RendererNotAvailableError
```

---

## 任务 5: 流水线调度

```
阅读 docs/SPEC.md 第 2 节和 CLAUDE.md，然后:

实现 src/core/pipeline.py:

class MapWizardPipeline:
    def __init__(self, config_manager: ConfigManager):
        self.boundary_mgr = BoundaryManager(...)
        self.gee_fetcher = GEEFetcher(...)
        self.cache_mgr = CacheManager(...)
        self.data_proc = DataProcessor()
    
    def run(self, config: RenderConfig, 
            progress_callback=None, log_callback=None) -> Path:
        """完整流水线:
        Step 1 (0-5%):   验证输入参数
        Step 2 (5-10%):  获取行政区边界
        Step 3 (10-60%): 检查缓存 → GEE 下载 → 裁剪
        Step 4 (60-95%): 调用渲染引擎
        Step 5 (95-100%): 输出结果
        """
    
    def _select_renderer(self, engine_name: str) -> BaseRenderer:
        """根据引擎名实例化渲染器"""
    
    def validate_config(self, config: RenderConfig) -> list[str]:
        """验证配置，返回错误列表 (空=有效)"""

同时实现 src/core/config_manager.py:

class ConfigManager:
    def __init__(self, config_path: Path = None):
    def load(self) -> dict:
    def save(self, data: dict):
    def get(self, key: str, default=None):
    def set(self, key: str, value):

config_path 默认为 ~/.rmw/config.json
```

---

## 任务 6: PyQt5 GUI

```
阅读 docs/SPEC.md 第 5 节，然后:

实现 GUI:

1. src/gui/main_window.py — 主窗口
   - 按 SPEC 5.2 节的界面布局
   - 省市下拉联动
   - 数据类型选择
   - 引擎选择 (不可用的自动置灰)
   - 输出目录选择
   - 日志面板 (QTextEdit, 只读, 自动滚动到底部)
   - 进度条 (QProgressBar)
   - "一键制作" 按钮 (运行时变为"取消")

2. src/gui/worker.py — 工作线程
   - 继承 QThread
   - 封装 pipeline.run()
   - 发射 progress / log / finished / error 信号

3. src/gui/gee_auth_dialog.py — GEE 认证对话框
   - Cloud Project ID 输入框
   - "开始认证" 按钮 → 调用 ee.Authenticate()
   - 认证状态显示

4. src/gui/shp_import_dialog.py — SHP 导入对话框
   - 文件选择
   - 预览边界范围
   - 名称输入

5. src/main.py — 应用入口

6. src/resources/style.qss — 样式表
   - 简洁现代风格
   - 主色调: #2E7D32 (与 GIS 绿色主题匹配)
   - 按钮圆角, 进度条自定义颜色

窗口标题: "研究区区位图自动制图工具 v1.0"
应用应能在没有 QGIS 的环境下启动 (引擎选项会置灰，但 GUI 正常运行)
```

---

## 任务 7: Cartopy 渲染引擎

```
实现 src/renderers/cartopy_renderer.py:

纯 Python 实现，不依赖 QGIS 或 ArcGIS。
使用 cartopy + matplotlib + geopandas。

class CartopyRenderer(BaseRenderer):
    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """
        使用 matplotlib figure 创建三级区位图:
        
        fig = plt.figure(figsize=(297/25.4, 210/25.4), dpi=config.dpi)
        
        (a) 中国全图: fig.add_axes([...], projection=ccrs.LambertConformal(...))
            - 绘制所有省份边界
            - 目标省份红色高亮
        
        (b) 省级图: fig.add_axes([...], projection=ccrs.PlateCarree())
            - 绘制省内城市边界
            - 目标城市红色高亮
        
        (c) 详图: fig.add_axes([...], projection=ccrs.PlateCarree())
            - 叠加 GEE 栅格数据 (ax.imshow)
            - 经纬网 (ax.gridlines)
            - 比例尺 (matplotlib_scalebar 或手动绘制)
            - 指北针 (手动绘制箭头 + "N")
            - 图例 (colorbar for DEM, 或文字说明 for Sentinel-2)
        
        面板标签 (a)(b)(c)
        标题
        底部信息栏
        
        fig.savefig(output_path, dpi=config.dpi, bbox_inches='tight')
        """

Cartopy 引擎的特殊处理:
- 比例尺需要手动绘制 (matplotlib_scalebar 包或自行计算)
- 指北针需要手动绘制箭头
- 中文字体: matplotlib 设置 rcParams['font.sans-serif'] = ['SimHei', 'Arial']
- DEM 叠加: 读取 GeoTIFF → apply_color_ramp → ax.imshow with extent
- 连接线: matplotlib patches (FancyArrowPatch 或 ConnectionPatch)
```

---

## 任务 8: ArcGIS Pro 渲染引擎

```
阅读 docs/SPEC.md 第 4.3 节（ArcGIS Pro 引擎详细设计），然后完成以下四个子任务。

### 8.1 实现 src/renderers/arcgis_renderer.py

class ArcGISRenderer(BaseRenderer):

    def __init__(self):
        self._propy_path = None
        self._arcgis_version = None

    def check_available(self) -> tuple[bool, str]:
        """检测 ArcGIS Pro 是否可用

        检测顺序:
        1. 检查 self._propy_path 缓存
        2. 读注册表 HKLM\SOFTWARE\ESRI\ArcGISPro\InstallDir
        3. 尝试常见路径: C:\Program Files\ArcGIS\Pro
        4. 找到后验证: subprocess 调用 propy.bat 执行
           python -c "import arcpy; print(arcpy.GetInstallInfo()['Version'])"
        5. 返回 (True, "ArcGIS Pro {version}") 或 (False, "未找到 ArcGIS Pro")

        Windows 注册表读取:
          import winreg
          key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\ESRI\ArcGISPro')
          install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
        """

    def _find_propy(self) -> Optional[Path]:
        """查找 propy.bat 路径，按 SPEC 4.3.1 节顺序检测"""

    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """通过 subprocess 调用 _arcgis_worker.py

        流程:
        1. 验证 propy.bat 可用（_find_propy）
        2. 将 config 序列化为 JSON 临时文件
           (Path 对象转为字符串，确保 Windows 路径正确)
           JSON 中额外包含:
             template_path: src/resources/templates/location_map_template.aprx 路径
             temp_dir:      系统临时目录
             output_dir:    config.output_path 的父目录
        3. subprocess.Popen(
               [str(propy_path), worker_script, '--config', config_json],
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE,
               text=True, encoding='utf-8'
           )
        4. 逐行读取 stdout，解析 JSON:
             {"step": "loading",  "progress": 10,  "message": "..."}  → progress_callback
             {"step": "done",     "progress": 100, "output": "..."}   → return Path(output)
             {"step": "error",    "message": "..."}                   → raise RenderFailedError
        5. 检查 returncode，非零则读 stderr 并抛出异常
        """

    def get_project_path(self) -> Optional[Path]:
        """返回最近一次渲染输出的 .aprx 文件路径"""


### 8.2 实现 src/renderers/_arcgis_worker.py

这个脚本在 ArcGIS Pro 的 Python 环境中独立运行，不导入主项目的任何模块。
与主进程通过 stdout JSON 行协议通信（见 SPEC 4.3.2 节）。

完整实现 SPEC 4.3.4 节的流程，关键要点:

1. 必须 import arcpy（只在 ArcGIS conda 环境中可用）
2. 所有进度通过 print(json.dumps(...), flush=True) 输出
3. 模板法（优先）: 打开预制 .aprx → 修改数据 → 导出
4. 全代码法（fallback，当 template_path 文件不存在时）:
   - 需要一个空白"种子" .aprx（可以打包一个极简空白模板）
   - aprx.createMap() × 3（China_Map / Province_Map / City_Map）
   - aprx.createLayout(297, 210, 'MILLIMETER')
   - layout.createMapFrame() × 3（用 arcpy.Polygon 定义精确位置，与 SPEC 4.2 节一致）
   - layout.createMapSurroundElement() 添加指北针、比例尺
   - aprx.createTextElement() 添加标题
5. 符号化（见 SPEC 4.3.5 节）:
   - DEM:        updateColorizer('RasterClassifyColorizer')
   - Hillshade:  updateColorizer('RasterStretchColorizer'), 灰度
   - Sentinel-2: updateColorizer('RasterRGBColorizer'), bands=[B4,B3,B2]
   - 行政区高亮: symbol.color + symbol.outlineColor
6. CIM Access 修改经纬网间距（见 SPEC 4.3.5 节示例）
7. 导出: arcpy.mp.CreateExportFormat() + layout.export()（见 SPEC 4.3.6 节）
8. 所有异常 try-except，通过 {"step": "error", "message": ...} 报告
9. 脚本末尾 del aprx 释放文件锁


### 8.3 创建 docs/arcgis_template_guide.md

内容包括:
- 如何在 ArcGIS Pro 中制作 location_map_template.aprx 模板（步骤截图说明）
- 模板中 Map 和 Layout 元素的命名规范（名称必须与 worker 脚本一致）:
    Maps:      China_Map, Province_Map, City_Map
    Layout:    LocationMap
    MapFrames: China_MapFrame, Province_MapFrame, City_MapFrame
    Text:      Title, Subtitle, DataSource
- 各 MapFrame 的精确位置和尺寸（与 SPEC 4.2 节一致，单位 mm）
- 模板制作完成后放置于 src/resources/templates/location_map_template.aprx
- 提供 fallback 空白种子 .aprx 的制作说明


### 8.4 编写测试 tests/test_arcgis_renderer.py

所有测试不依赖 ArcGIS Pro 安装，全部用 mock:

- test_check_available_no_arcgis:
    mock subprocess 返回 FileNotFoundError
    断言返回 (False, ...) 且 reason 中含"未找到"字样

- test_check_available_with_arcgis:
    mock subprocess stdout 返回 "3.4.0"
    断言返回 (True, "ArcGIS Pro 3.4.0")

- test_render_calls_subprocess:
    mock Popen，mock stdout 输出 done JSON
    断言 Popen 被调用，传入的参数包含 propy_bat 路径和 worker 脚本路径

- test_render_parses_progress:
    mock stdout 输出多行 JSON（loading/data/render/export/done）
    断言 progress_callback 被正确调用，次数和参数与 JSON 一致

- test_render_handles_error:
    mock stdout 输出 {"step": "error", "message": "arcpy 崩溃"}
    断言抛出 RenderFailedError，错误信息包含"arcpy 崩溃"

- test_config_serialization:
    构造一个含 Path 对象的 RenderConfig
    验证序列化后 JSON 可正常 json.loads()，且 Path 已转为字符串
```

---

## 任务 9: 测试与文档

```
1. 补充所有模块的单元测试，确保 pytest 可以在无 QGIS 环境下通过
   (PyQGIS 相关测试标记为 @pytest.mark.skipif)

2. 创建 tests/fixtures/sample_dem.tif:
   用 rasterio + numpy 生成一个 100x100 像素的假 DEM GeoTIFF
   覆盖北京附近的一小块区域 (116.0-116.5°E, 39.5-40.0°N)

3. 完善 README.md:
   - 项目截图 (如果有)
   - 快速开始 (conda install → python main.py)
   - 详细安装说明 (QGIS 环境配置)
   - GEE 账号配置教程
   - 使用说明 (图文)
   - 贡献指南
   - 许可证

4. 创建 CONTRIBUTING.md:
   - 开发环境搭建
   - 代码规范
   - PR 流程
   - Issue 模板

5. 创建 docs/gee_setup_guide.md:
   - GEE 注册教程
   - Cloud Project 创建
   - Earth Engine API 启用
   - 非商业验证流程说明
```

---

## 补充说明

### 开发顺序建议

按上述任务编号 0→1→2→3→4→5→6→7→8→9 顺序开发。
每完成一个任务，运行 `pytest` 确认不破坏已有功能。

### 如何使用这些提示词

1. 用 Claude Code 打开项目根目录
2. Claude Code 会自动读取 `.claude/CLAUDE.md`
3. 按顺序粘贴每个任务的提示词
4. Claude Code 会实现对应模块并运行测试
5. 需要时让 Claude Code 读取 `docs/SPEC.md` 获取详细参数

### 重要原则

- 每个模块必须可独立测试
- 不要硬编码路径，统一用 Path 对象
- GEE 下载要有缓存，避免重复下载
- GUI 保持响应，耗时操作走 QThread
- 支持取消操作 (通过 threading.Event 或 QThread 中断)
- 所有用户可见文本都可国际化 (self.tr() 或 QCoreApplication.translate)
