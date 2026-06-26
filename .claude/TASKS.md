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

## 任务 4: QGIS 渲染引擎

```
阅读 docs/SPEC.md 第 4 节（全部），然后:

实现 src/renderers/qgis_renderer.py:

这是项目最核心的模块。它要使用 PyQGIS 的 QgsLayout 系统
生成一张包含三级区位图的高清地图。

class QGISRenderer(BaseRenderer):
    def __init__(self):
        self._qgs = None  # QgsApplication 实例
    
    def _init_qgis(self):
        """初始化 PyQGIS (独立模式，无 GUI)
        自动检测 QGIS 安装路径
        """
    
    def check_available(self) -> tuple[bool, str]:
        """检查 QGIS 是否可用"""
    
    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """完整渲染流程:
        1. 初始化 QGIS
        2. 创建 QgsProject
        3. 加载矢量图层 (国界、省界、市界)
        4. 加载栅格图层 (DEM/影像)
        5. 设置符号化
        6. 创建 QgsPrintLayout (A4 横版)
        7. 添加三个 QgsLayoutItemMap (中国、省、市)
        8. 添加标题、经纬网、比例尺、指北针、图例
        9. 导出
        """
    
    def _setup_vector_layers(self, project, config):
        """加载并符号化矢量图层"""
    
    def _setup_raster_layer(self, project, config):
        """加载并符号化栅格图层
        DEM: QgsRasterShader + QgsColorRampShader 分层设色
        Hillshade: 灰度渲染
        Sentinel-2: RGB 真彩色
        """
    
    def _create_layout(self, project, config) -> QgsPrintLayout:
        """创建排版布局，按 SPEC 第 4.2 节的精确尺寸:
        - 页面: 297×210mm
        - (a) 中国全图: 左上 90×78mm, Lambert Conformal Conic
        - (b) 省级图: 左下 90×62mm
        - (c) 研究区详图: 右侧 182×155mm
        - 标题栏: 顶部右侧 12mm 高
        - 底部信息栏: 8mm 高
        """
    
    def _add_map_decorations(self, layout, map_item, config):
        """添加经纬网、比例尺、指北针、图例"""
    
    def _add_connection_lines(self, layout, config):
        """添加从全国图指向省图、省图指向市图的连接线框"""
    
    def _export(self, layout, config) -> Path:
        """使用 QgsLayoutExporter 导出"""

关键实现注意:
- QgsLayoutItemMap.setExtent() 设置每个面板的显示范围
- QgsLayoutItemMapGrid 添加经纬网
- QgsLayoutItemScaleBar 添加比例尺
- QgsLayoutItemPicture 添加指北针 SVG
- QgsLayoutItemLabel 添加标题文本
- QgsLayoutItemLegend 添加图例
- 中国全图需要用 Lambert Conformal Conic 投影 (EPSG:4488 或自定义)
- 省和市面板可以用 PlateCarree
- 研究区高亮: 给目标省份/城市加红色填充半透明 + 红色边框
- 字体: 优先使用 SimHei/SimSun，fallback 到 Arial
- 输出 DPI: 从 config.dpi 读取

由于 PyQGIS 环境可能不可用 (在没有 QGIS 的机器上开发),
先写完整代码结构，所有 PyQGIS 调用封装在 try-except 中，
缺少 QGIS 时 check_available() 返回 False。
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
实现 src/renderers/arcgis_renderer.py 和 src/renderers/_arcgis_worker.py:

ArcGIS Pro 模式通过 subprocess 调用 ArcGIS 的 Python 环境。

arcgis_renderer.py:
class ArcGISRenderer(BaseRenderer):
    def check_available(self) -> tuple[bool, str]:
        """通过 subprocess 检测 arcpy 可用性
        调用 ArcGIS Pro 的 python.exe 执行:
        python -c "import arcpy; print(arcpy.GetInstallInfo()['Version'])"
        """
    
    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """
        1. 将 config 序列化为 JSON 临时文件
        2. subprocess.Popen 调用 _arcgis_worker.py
        3. 读取 stdout 获取进度
        4. 等待完成，返回输出路径
        """

_arcgis_worker.py (独立脚本，在 ArcGIS Python 环境中运行):
    """
    1. 读取 config JSON
    2. 创建 ArcGISProject
    3. aprx.createLayout() 创建布局
    4. layout.createMapFrame() 创建三个地图框
    5. 加载图层、设置符号化
    6. layout.exportToJPEG / exportToPDF
    7. 向 stdout 打印进度 JSON: {"progress": 50, "message": "渲染中..."}
    """
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
