# 🗺 研究区区位图自动制图工具

**Region Map Wizard** — 选省市、下数据、一键出图

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

---

## 这是什么？

一个开源的桌面工具，帮你自动生成科研论文中常见的**三级研究区区位图**（中国 → 省 → 市），并可叠加 DEM 高程设色、山体阴影或 Sentinel-2 卫星影像。

传统做法需要在 ArcGIS Pro 或 QGIS 中手动操作数十步：下载数据、裁剪、设符号、排版、加经纬网、加比例尺……而这个工具把一切简化为：**选省市 → 点按钮 → 拿图**。

## 核心功能

- **三级区位图**：自动排版中国→省→城市三个尺度的地图，带精确连接指示线
- **GEE 数据集成**：一键从 Google Earth Engine 下载 DEM / 山体阴影 / Sentinel-2
- **多引擎渲染**：支持 Cartopy (纯 Python) / QGIS (PyQGIS) / ArcGIS Pro 三种出图引擎
- **出图即论文**：经纬网、比例尺、指北针、学术斑马框、标题一步到位，300 DPI 高清输出
- **自定义研究区**：除了中国省市选择，还可上传自定义 SHP 文件（跨省大区域自动切换两图模式）
- **智能缓存**：已下载的 GEE 数据自动缓存，不重复下载
- **独立可执行文件**：支持 PyInstaller 打包为无需安装 Python 的单目录 exe

## 快速开始

### 方式一：直接运行 exe（推荐）

从 [Releases](../../releases) 下载最新版本，解压后双击 `RegionMapWizard.exe` 即可，无需安装 Python 或任何依赖。

### 方式二：从源码运行

```bash
# 1. 克隆仓库
git clone <repo-url>
cd region-map-tool

# 2. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate       # Windows
pip install -r requirements.txt

# 3. 配置 GEE (首次需要)
#    参见 docs/gee_setup_guide.md

# 4. 启动
python -m src.main
# 或直接双击 启动应用.bat
```

### 自行打包 exe

```bash
pip install pyinstaller
pyinstaller --clean --noconfirm rmw.spec
# 输出在 dist/RegionMapWizard/
```

### GEE 配置

首次使用需要完成 Google Earth Engine 认证，详见 [GEE 配置教程](docs/gee_setup_guide.md)。

## 出图效果

> 截图待补充

## 项目进度

### 已完成

- [x] PyQt5 GUI 框架（主窗口、GEE 认证对话框、自定义 SHP 导入对话框）
- [x] Google Earth Engine 数据获取（DEM / 山体阴影 / Sentinel-2）
- [x] 行政边界数据管理（`china_admin.gpkg`，国/省/市三图层）
- [x] **Cartopy 渲染引擎**（当前主力引擎）
  - [x] A4 横版三面板布局（中国全图 / 省级图 / 研究区详图）
  - [x] 精确缩放连接线（从实际渲染坐标轴边界出发，解决 cartopy aspect 收缩问题）
  - [x] 学术斑马边框、经纬网、比例尺、指北针
  - [x] 大范围自定义 SHP 自动切换两图模式（跳过省级面板）
  - [x] 自定义 SHP 支持中文路径、完整格式校验（缺文件 / 非面 / 无坐标系 等类型化异常）
  - [x] Lambert 等角圆锥投影中国全图 + 适当 extent 配置
- [x] 后台引擎探测线程（避免启动时 GUI 阻塞）
- [x] PyInstaller 独立 exe 打包（含 GDAL/GEOS/PROJ DLL 自动注册）
- [x] **ArcGIS Pro 渲染引擎**（架构实现完成，待 ArcGIS Pro 环境联调）
  - [x] 注册表自动检测 + propy.bat 环境发现
  - [x] subprocess 进程隔离（主进程不 import arcpy）
  - [x] JSON 行协议进度通信（stdout UTF-8 强制编码，解决 GBK 乱码）
  - [x] 三图框布局（模板法优先 + 全代码 fallback）
  - [x] 符号化：DEM 分层设色 / 山体阴影灰度 / Sentinel-2 RGB
  - [x] CIM Access 经纬网间距设置
  - [x] ArcGIS Pro 3.4+ `CreateExportFormat` 导出 API
  - [x] 模板制作指南 (`docs/arcgis_template_guide.md`)

### 开发计划

#### 近期

- [ ] 渲染结果预览（在 GUI 中嵌入图片查看器）
- [ ] 导出格式选择（JPG / PNG / PDF / SVG）
- [ ] 图名、颜色、字体等样式参数开放给用户配置
- [ ] 支持手动调整三个面板的经纬度范围

#### 中期 — QGIS 适配（架构实现完成，待实机联调）

- [x] `QGISRenderer`：与 ArcGIS 相同的 subprocess 架构（`python-qgis.bat` → `_qgis_worker.py`），彻底解决 Windows 环境隔离问题
- [x] `_qgis_worker.py`：QgsApplication 独立模式 + QgsPrintLayout 三图框 + QgsLayoutExporter
- [x] 注册表 + 常见路径自动检测 `python-qgis.bat`（OSGeo4W / 独立安装版，QGIS 3.28–3.40）
- [x] JSON 行协议进度通信（stdout UTF-8 强制编码，解决 GBK 乱码）
- [x] mock 测试，不依赖 QGIS 安装（9 个测试全部通过）
- [ ] QGIS 实机测试与细节调整
- [ ] 提供 QGIS 插件形式的分发包（`.zip` 插件格式）

#### 中期 — ArcGIS Pro 适配（框架已就绪，待实机联调）

- [x] 基于 **arcpy** 实现 `ArcGISRenderer`，通过 `subprocess` 调用 ArcGIS Pro Python 环境
- [x] 自动检测 ArcGIS Pro 安装路径（注册表 → 常见路径 → 环境变量）
- [ ] 制作预制 `.aprx` 模板并打包（见 [模板制作指南](docs/arcgis_template_guide.md)）
- [ ] ArcGIS Pro 实机测试与符号化细节调整

#### 长期

- [ ] 多语言界面（中/英）
- [ ] 批量制图（CSV 输入多个城市，一键批出）
- [ ] 插件市场 / 自定义地图模板导入

## 开发心得

记录了开发过程中遇到的 Bug、根因分析与解决方案，包括：

- PyInstaller 打包 GIS 包的 DLL 加载问题
- Cartopy GeoAxes aspect 收缩导致连线偏移
- pipeline 与 renderer 的数据传递边界设计
- OOM 问题定位与内存优化

详见 [docs/DEV_NOTES.md](docs/DEV_NOTES.md)

## 贡献

欢迎贡献代码、报告 Bug、改进文档！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

GPL-3.0 — 与 QGIS 许可证兼容。
