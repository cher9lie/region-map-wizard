# Claude Code 任务: ArcGIS Pro 渲染引擎详细设计

## 背景

经过对 ESRI 官方开发文档 (pro.arcgis.com) 的深度调研，确认了以下关键事实：

1. **arcpy.mp 支持完全独立于 ArcGIS Pro GUI 运行**。只要机器上安装了 ArcGIS Pro（提供 arcpy 运行环境），Python 脚本可以在应用关闭的情况下完成「创建地图 → 加载数据 → 符号化 → 排版 → 导出」全流程。ESRI 原文："You can modify the contents of these files in the application or without the application being open."

2. **从 ArcGIS Pro 3.2 起，arcpy.mp 可以通过代码从零创建排版元素**，包括：
   - `ArcGISProject.createMap(name, map_type)` — 创建地图
   - `ArcGISProject.createLayout(width, height, page_units)` — 创建排版页面
   - `Layout.createMapFrame(geometry, map, name)` — 创建地图框（用 arcpy.Polygon 定义位置和大小）
   - `Layout.createMapSurroundElement(geometry, type, mapframe, style_item, name)` — 创建指北针 / 比例尺 / 图例 / 经纬网格，type 可选值: "NORTH_ARROW" / "SCALE_BAR" / "LEGEND" / "GRID" / "DUAL_SCALE_BAR"
   - `ArcGISProject.createTextElement(layout, geometry, name)` — 创建文字元素
   - `ArcGISProject.createGraphicElement(layout, geometry, name)` — 创建图形元素
   - `ArcGISProject.createPictureElement(layout, geometry, picture_path, name)` — 创建图片元素
   - 样式引用: `ArcGISProject.listStyleItems('ArcGIS 2D', 'North_Arrow', 'Compass North 1')[0]` 获取系统内置样式

3. **但 arcpy.mp 不能凭空创建 .aprx 项目文件**。ESRI 原文: "arcpy.mp does not allow you to completely author new projects." 必须基于一个已存在的 .aprx 文件操作。所以我们需要预制一个空白模板 .aprx 打包到软件中。

4. **独立脚本与应用内脚本的导出效果完全一致**。ESRI 原文: "MapFrame export has all of the sizing information persisted in the element so scripts run from inside the application or run as stand-alone scripts outside the application will produce the same export result."

5. **独立脚本不能使用的功能**：`openView()`、`closeViews()`、`'CURRENT'` 关键字。这些仅在 ArcGIS Pro 应用内可用。我们不需要这些。

6. **独立脚本必须通过 propy.bat 或 ArcGIS Pro 的 conda 环境启动**。路径为 `C:\Program Files\ArcGIS\Pro\bin\Python\scripts\propy.bat`，或直接调用 `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`。

7. **Python CIM Access** 可以访问 arcpy.mp API 未暴露的底层属性（如经纬网间距、字体大小、边框符号等），通过 `getDefinition('V3')` 和 `setDefinition()` 实现。

8. **ArcGIS Pro 3.4+ 新增了 `export()` 统一导出方法和 `CreateExportFormat()` 工厂函数**，替代旧的 `exportToPDF()` / `exportToJPEG()` 等方法。新方法支持 PDF / JPEG / PNG / BMP / TIFF / SVG / EPS / EMF / GIF / AIX 共 11 种格式。

## 你的任务

请阅读 `docs/SPEC.md` 和 `.claude/CLAUDE.md`，然后完成以下工作：

### 1. 更新 docs/SPEC.md

在第 4 节「渲染引擎层」中，将 ArcGIS Pro 部分从简略描述扩展为与 QGIS 引擎同等详细程度的完整设计。具体包括：

#### 4.3 ArcGIS Pro 引擎 — 详细设计

**4.3.1 环境检测与初始化**

编写 ArcGIS Pro 环境检测逻辑，按以下顺序查找：
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

**4.3.2 进程模型**

详细描述主进程 (PyQt5 GUI) 与 arcpy 工作进程之间的通信协议：
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
  │     │      {"step": "loading", "progress": 10, "message": "加载模板..."}
  │     │      {"step": "data", "progress": 30, "message": "加载栅格数据..."}
  │     │      {"step": "render", "progress": 70, "message": "渲染排版..."}
  │     │      {"step": "export", "progress": 90, "message": "导出 JPG..."}
  │     │      {"step": "done", "progress": 100, "output": "C:\\output\\map.jpg"}
  │     │    - 异常时输出:
  │     │      {"step": "error", "message": "arcpy 错误详情"}
  │     │
  │  3. 主进程逐行读取 stdout，解析 JSON，更新进度条
  │  4. 子进程结束后，主进程获取输出文件路径
```

**4.3.3 模板 .aprx 设计**

描述预制模板的结构——两种策略对比：

策略 A（模板法，推荐）：
- 预先在 ArcGIS Pro 中手动制作一个区位图排版模板 `location_map_template.aprx`
- 包含 3 个 Map（China_Map / Province_Map / City_Map）
- 包含 1 个 Layout（A4 横版 297×210mm）
  - 3 个 MapFrame（对应三个 Map，位置尺寸与 SPEC 4.2 节一致）
  - 预设的指北针、比例尺、图例、标题文本框
- 脚本运行时：复制模板 → 修改数据源 → 调整范围 → 修改文本 → 导出
- 优势：排版美观度有保证、代码简单
- 劣势：模板制作需要 ArcGIS Pro、模板文件 ~5-10MB

策略 B（全代码创建，ArcGIS Pro ≥ 3.2）：
- 用 createLayout + createMapFrame + createMapSurroundElement 全部从代码创建
- 需要通过 CIM Access 修改经纬网间距、字体等细节属性
- 优势：灵活、无外部模板文件依赖
- 劣势：代码量大、CIM 操作复杂、样式调整困难

推荐混合策略：提供预制模板（首选），同时实现 fallback 的全代码创建路径（当模板文件缺失时自动使用）。

**4.3.4 _arcgis_worker.py 完整流程**

详细描述 worker 脚本中的 arcpy 调用序列（伪代码级别）：

```python
# _arcgis_worker.py — 在 ArcGIS Pro Python 环境中运行
import arcpy, json, sys, os

def report(step, progress, message, **kwargs):
    """向 stdout 输出 JSON 进度"""
    print(json.dumps({"step": step, "progress": progress, "message": message, **kwargs}, ensure_ascii=False), flush=True)

def main(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 1. 复制模板并打开
    report("loading", 5, "打开 ArcGIS Pro 项目模板...")
    template_aprx = config['template_path']
    work_aprx = os.path.join(config['temp_dir'], 'work.aprx')
    # 复制模板文件
    import shutil
    shutil.copy2(template_aprx, work_aprx)
    aprx = arcpy.mp.ArcGISProject(work_aprx)
    
    # 2. 获取地图和布局引用
    china_map = aprx.listMaps('China_Map')[0]
    province_map = aprx.listMaps('Province_Map')[0]
    city_map = aprx.listMaps('City_Map')[0]
    layout = aprx.listLayouts('LocationMap')[0]
    
    # 3. 加载数据到各地图
    report("data", 20, "加载行政区边界...")
    # 加载矢量边界
    china_map.addDataFromPath(config['country_boundary'])
    province_map.addDataFromPath(config['province_boundary'])
    city_map.addDataFromPath(config['city_boundary'])
    
    # 加载栅格数据到城市地图
    if config.get('raster_path'):
        report("data", 35, "加载栅格数据...")
        city_map.addDataFromPath(config['raster_path'])
    
    # 4. 设置符号化
    report("symbolize", 45, "设置符号化...")
    # 对 DEM 应用分层设色
    # 对省份应用高亮
    # 对城市边界应用红色边框
    for lyr in city_map.listLayers():
        if lyr.isRasterLayer:
            sym = lyr.symbology
            if config['data_type'] == 'dem':
                sym.updateColorizer('RasterClassifyColorizer')
                # ... 设置色带
            lyr.symbology = sym
    
    # 5. 设置各地图框范围
    report("extent", 60, "设置地图范围...")
    china_mf = layout.listElements('MapFrame_Element', 'China_MapFrame')[0]
    province_mf = layout.listElements('MapFrame_Element', 'Province_MapFrame')[0]
    city_mf = layout.listElements('MapFrame_Element', 'City_MapFrame')[0]
    
    # 城市地图框缩放到城市边界范围
    city_lyr = city_map.listLayers(config['city_name'])[0]
    ext = city_mf.getLayerExtent(city_lyr, False, True)
    city_mf.camera.setExtent(ext)
    city_mf.camera.scale *= 1.1  # 留边距
    
    # 6. 更新文本元素
    report("text", 70, "更新标注...")
    title = layout.listElements('TEXT_ELEMENT', 'Title')[0]
    title.text = f"{config['province_name']}{config['city_name']}研究区区位图"
    
    # 7. 经纬网格 (通过 CIM 修改间距)
    report("grid", 80, "设置经纬网...")
    # city_mf.addGrid(...) 或通过 CIM 修改已有网格
    
    # 8. 保存项目副本 (供用户后续编辑)
    report("save", 85, "保存 ArcGIS Pro 工程...")
    output_aprx = os.path.join(config['output_dir'], 
        f"{config['province_name']}_{config['city_name']}_区位图.aprx")
    aprx.saveACopy(output_aprx)
    
    # 9. 导出图片
    report("export", 90, "导出图片...")
    output_path = os.path.join(config['output_dir'],
        f"{config['province_name']}_{config['city_name']}_区位图.{config['format']}")
    
    if config['format'].lower() == 'pdf':
        fmt = arcpy.mp.CreateExportFormat('PDF', output_path)
        fmt.resolution = config.get('dpi', 300)
    elif config['format'].lower() in ('jpg', 'jpeg'):
        fmt = arcpy.mp.CreateExportFormat('JPEG', output_path)
        fmt.resolution = config.get('dpi', 300)
    elif config['format'].lower() == 'png':
        fmt = arcpy.mp.CreateExportFormat('PNG', output_path)
        fmt.resolution = config.get('dpi', 300)
    elif config['format'].lower() in ('tif', 'tiff'):
        fmt = arcpy.mp.CreateExportFormat('TIFF', output_path)
        fmt.resolution = config.get('dpi', 300)
    
    layout.export(fmt)
    
    report("done", 100, "完成", output=output_path, project=output_aprx)
    
    del aprx  # 释放锁

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    try:
        main(args.config)
    except Exception as e:
        print(json.dumps({"step": "error", "message": str(e)}, ensure_ascii=False), flush=True)
        sys.exit(1)
```

**4.3.5 arcpy 符号化 API 参考**

列出我们需要用到的关键 arcpy 符号化方法：

| 操作 | API | 说明 |
|------|-----|------|
| DEM 分层设色 | `lyr.symbology.updateColorizer('RasterClassifyColorizer')` | 然后设置 classBreaks 和色带 |
| DEM 拉伸渲染 | `lyr.symbology.updateColorizer('RasterStretchColorizer')` | 单波段拉伸 |
| RGB 真彩色 | `lyr.symbology.updateColorizer('RasterRGBColorizer')` | Sentinel-2 B4/B3/B2 |
| 矢量填充 | `lyr.symbology.renderer.symbol.color` | 修改面填充颜色 |
| 矢量边框 | `lyr.symbology.renderer.symbol.outlineColor` | 修改边框颜色和宽度 |
| 透明度 | `lyr.transparency = 50` | 图层透明度 |
| 定义查询 | `lyr.definitionQuery = "adcode = '130000'"` | 仅显示特定要素 |

对于 arcpy.mp API 未覆盖的属性，使用 Python CIM Access：
```python
lyt_cim = layout.getDefinition('V3')
for elm in lyt_cim.elements:
    if elm.name == 'City_MapFrame':
        # 修改经纬网间距
        for grid in elm.grids:
            grid.gridLineOrigin.x = 0.5  # 经度间隔
            grid.gridLineOrigin.y = 0.5  # 纬度间隔
layout.setDefinition(lyt_cim)
```

**4.3.6 导出格式与参数**

ArcGIS Pro 3.4+ 使用 `CreateExportFormat` + `layout.export(fmt)`:

| 格式 | CreateExportFormat 参数 | 关键属性 |
|------|------------------------|---------|
| PDF | `'PDF'` | resolution, embedFonts=True, imageCompressionQuality, georefInfo |
| JPEG | `'JPEG'` | resolution, jpegQuality(0-100) |
| PNG | `'PNG'` | resolution |
| TIFF | `'TIFF'` | resolution, geoTiffTags=True |
| SVG | `'SVG'` | resolution, compressVectorGraphics |
| BMP | `'BMP'` | resolution |

**4.3.7 ArcGIS 引擎优势与限制**

优势：
- 出图质量是三个引擎中最高的（ArcGIS Pro 渲染引擎成熟度最高）
- 丰富的内置样式库（North_Arrow、Scale_bar 各有数十种预设）
- 输出可编辑的 .aprx 项目文件，用户可继续在 ArcGIS Pro 中微调
- CIM Access 提供了极深度的自定义能力

限制：
- 用户必须安装 ArcGIS Pro（商业软件，需授权）
- arcpy 只能在 ArcGIS Pro 的 conda 环境中运行，不能安装到系统 Python
- 通过 subprocess 调用，主进程无法直接 import arcpy
- 不能凭空创建 .aprx，需要预制模板文件
- Windows 独占（ArcGIS Pro 不支持 macOS/Linux）

### 2. 更新 .claude/TASKS.md

将「任务 8: ArcGIS Pro 渲染引擎」替换为以下更详细的版本——基于上述调研结果重写：

```
## 任务 8: ArcGIS Pro 渲染引擎

阅读 docs/SPEC.md 第 4.3 节（ArcGIS Pro 引擎详细设计），然后:

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
        
        Windows 注册表读取用 winreg 模块:
          import winreg
          key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\ESRI\ArcGISPro')
          install_dir, _ = winreg.QueryValueEx(key, 'InstallDir')
        """
    
    def _find_propy(self) -> Optional[Path]:
        """查找 propy.bat 路径"""
    
    def render(self, config: RenderConfig, progress_callback=None) -> Path:
        """通过 subprocess 调用 _arcgis_worker.py
        
        流程:
        1. 验证 propy.bat 可用
        2. 将 config 序列化为 JSON 临时文件
           (Path 对象转为字符串, 确保 Windows 路径正确)
        3. 确定模板 .aprx 路径:
           优先用 src/resources/templates/location_map_template.aprx
           不存在则让 worker 脚本全代码创建
        4. subprocess.Popen(
               [str(propy_path), worker_script, '--config', config_json],
               stdout=subprocess.PIPE,
               stderr=subprocess.PIPE,
               text=True, encoding='utf-8'
           )
        5. 逐行读取 stdout:
           for line in process.stdout:
               data = json.loads(line)
               if data['step'] == 'error':
                   raise RenderError(data['message'])
               if data['step'] == 'done':
                   return Path(data['output'])
               if progress_callback:
                   progress_callback(data['progress'], data['message'])
        6. 检查 returncode, 非零则读取 stderr 报错
        """
    
    def get_project_path(self) -> Optional[Path]:
        """返回输出的 .aprx 文件路径"""

### 8.2 实现 src/renderers/_arcgis_worker.py

这个脚本在 ArcGIS Pro 的 Python 环境中独立运行，不导入主项目的任何模块。
它通过 stdin/stdout JSON 协议与主进程通信。

完整实现上述 SPEC 4.3.4 节中的伪代码，关键要点:

1. 必须 import arcpy（只在 ArcGIS conda 环境中可用）
2. 所有进度通过 print(json.dumps(...), flush=True) 输出
3. 模板法：打开预制 .aprx → 修改 → 导出
4. 全代码法（fallback）：
   - 需要一个"种子" .aprx（可以是完全空白的）
   - aprx.createMap() × 3
   - aprx.createLayout(297, 210, 'MILLIMETER')
   - layout.createMapFrame() × 3 (用 arcpy.Polygon 定义精确位置)
   - layout.createMapSurroundElement() 添加指北针、比例尺
   - aprx.createTextElement() 添加标题
5. 符号化:
   - DEM: updateColorizer('RasterClassifyColorizer')
   - Hillshade: updateColorizer('RasterStretchColorizer'), 灰度
   - Sentinel-2: updateColorizer('RasterRGBColorizer'), bands=[3,2,1]
   - 行政区高亮: 修改 symbol.color 和 outlineColor
6. CIM Access 修改经纬网间距:
   layout.getDefinition('V3') → 修改 grid 属性 → layout.setDefinition()
7. 导出: arcpy.mp.CreateExportFormat() + layout.export()
8. 异常全部 try-except, 通过 stdout JSON 报告
9. 脚本末尾 del aprx 释放文件锁

### 8.3 创建模板项目文件说明

创建 docs/arcgis_template_guide.md:
- 如何在 ArcGIS Pro 中制作 location_map_template.aprx 模板
- 模板中 Map 和 Layout 元素的命名规范
- 模板中各元素的精确位置和尺寸（与 SPEC 4.2 节一致）
- 每个 MapFrame 关联的 Map 名称
- 文本元素的名称（Title, Subtitle, DataSource 等）
- 模板制作完成后放置于 src/resources/templates/

### 8.4 编写测试

tests/test_arcgis_renderer.py:
- test_check_available_no_arcgis: mock subprocess 返回 FileNotFoundError, 验证返回 (False, ...)
- test_check_available_with_arcgis: mock subprocess 返回 "3.4.0", 验证返回 (True, "ArcGIS Pro 3.4.0")
- test_render_calls_subprocess: mock Popen, 验证传入的参数正确
- test_render_parses_progress: mock stdout 输出多行 JSON, 验证 progress_callback 被正确调用
- test_render_handles_error: mock stdout 输出 error JSON, 验证抛出 RenderError
- test_config_serialization: 验证 RenderConfig 正确序列化为 JSON (Path → str)

所有测试不依赖 ArcGIS Pro 安装，全部用 mock。
```

### 3. 更新 .claude/CLAUDE.md

在 CLAUDE.md 的「PyQGIS 注意事项」之后添加一个新小节：

```
### ArcGIS Pro (arcpy) 注意事项
- arcpy 不能安装到系统 Python，只存在于 ArcGIS Pro 的 conda 环境中
- 所有 arcpy 代码必须放在 _arcgis_worker.py 中，通过 subprocess 调用
- 主项目代码（gui/, core/, renderers/arcgis_renderer.py）绝不能 import arcpy
- _arcgis_worker.py 是一个完全独立的脚本，不导入主项目的任何模块
- 它与主进程通过 stdout JSON 行协议通信
- 调用入口是 propy.bat（不是直接调用 python.exe）
- 预制模板 .aprx 文件放在 src/resources/templates/
- 测试用 mock subprocess，不依赖 ArcGIS Pro 安装
- ArcGIS Pro 3.4+ 使用 CreateExportFormat + export() 替代旧的 exportToPDF() 等方法
```

### 4. 同步检查

更新完成后，确保以下一致性:
- SPEC.md 中 BaseRenderer 抽象接口没有因 ArcGIS 特殊需求而变化（不应该变）
- TASKS.md 中任务 8 的提示词引用的 SPEC 节号正确
- arcgis_renderer.py 的 render() 方法签名与 base.py 中的 BaseRenderer.render() 一致
- _arcgis_worker.py 的 JSON 协议格式在 SPEC 和 TASKS 中描述一致

运行 ruff check 确认所有文件格式规范。
