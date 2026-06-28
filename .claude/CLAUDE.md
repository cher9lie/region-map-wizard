# Region Map Wizard — Claude Code 开发指令

## 项目概述

你正在开发一个名为 **Region Map Wizard (rmw)** 的开源桌面 GIS 工具。它的核心功能是：用户选择中国的省/市（或上传自定义 SHP），一键从 Google Earth Engine 下载遥感数据（DEM / 山体阴影 / Sentinel-2），然后自动生成科研论文级别的三级研究区区位图（中国→省→城市），输出高清 JPG/PNG/PDF。

## 技术栈

- **GUI**: PyQt5 (与 QGIS 同 Qt 生态)
- **GEE 数据获取**: earthengine-api + geemap
- **栅格处理**: rasterio + numpy
- **矢量处理**: geopandas + shapely
- **渲染引擎 (优先)**: PyQGIS (QgsLayout, QgsLayoutItemMap, QgsLayoutExporter)
- **渲染引擎 (备选)**: cartopy + matplotlib, arcpy (subprocess)
- **打包**: conda 环境 / QGIS 插件

## 关键文件

- `docs/SPEC.md`: 完整技术规格书，包含所有数据格式、接口定义、排版参数。**开发前必读此文件。**
- `src/renderers/base.py`: 渲染引擎抽象基类和 RenderConfig 数据类定义
- `src/data/cities.json`: 省市层级索引 (adcode + 名称 + 中心坐标)
- `src/data/china_admin.gpkg`: GeoPackage 行政边界 (country/province/city 三图层)
- `src/data/color_ramps.json`: DEM 色带定义

## 开发规范

### 代码风格
- Python 3.10+ 语法，使用 type hints
- 使用 dataclass 和 Enum 替代裸字典/字符串常量
- 变量名和注释用英文，用户可见文本用中文
- 遵循 PEP 8，使用 ruff 格式化
- 每个模块顶部写 docstring 说明职责
- 路径操作统一使用 pathlib.Path
- 所有文件操作使用 UTF-8 编码

### 异常处理
- 自定义异常类在 `src/core/exceptions.py`
- GEE 操作必须有超时和重试
- 文件 I/O 必须 try-except
- 向 GUI 汇报错误用 pyqtSignal，不要在工作线程弹对话框

### PyQGIS 注意事项
- QgsApplication 初始化必须在所有 PyQGIS 调用之前
- 独立运行模式: `QgsApplication([], False)` (无 GUI)
- 初始化后调用 `qgs.initQgis()`，退出时调用 `qgs.exitQgis()`
- QGIS 安装路径通过 `QgsApplication.setPrefixPath()` 设置
- Windows 上需要正确设置 PATH 和 PYTHONPATH 指向 OSGeo4W

### ArcGIS Pro (arcpy) 注意事项
- arcpy 不能安装到系统 Python，只存在于 ArcGIS Pro 的 conda 环境中
- 所有 arcpy 代码必须放在 `src/renderers/_arcgis_worker.py` 中，通过 subprocess 调用
- 主项目代码（gui/, core/, renderers/arcgis_renderer.py）绝不能 `import arcpy`
- `_arcgis_worker.py` 是完全独立的脚本，不导入主项目的任何模块
- 与主进程通过 stdout JSON 行协议通信（每行一个 JSON 对象，`flush=True`）
- 调用入口是 `propy.bat`，不是直接调用 `python.exe`
- 不能凭空创建 `.aprx`，预制模板放在 `src/resources/templates/`
- 测试用 mock subprocess，不依赖 ArcGIS Pro 安装
- ArcGIS Pro 3.4+ 使用 `CreateExportFormat()` + `layout.export()` 替代旧的 `exportToPDF()` 等方法
- 独立脚本不可使用 `openView()`、`closeViews()`、`'CURRENT'` 关键字（仅 GUI 内可用）

### 测试
- 测试文件放在 `tests/`
- 用 pytest
- GEE 测试用 mock（不实际调用 API）
- fixtures 放在 `tests/fixtures/`
