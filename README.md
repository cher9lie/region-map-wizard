# 🗺 研究区区位图自动制图工具

**Region Map Wizard** — 选省市、下数据、一键出图

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

---

## 这是什么？

一个开源的桌面工具，帮你自动生成科研论文中常见的**三级研究区区位图**（中国 → 省 → 市），并可叠加 DEM 高程设色、山体阴影或 Sentinel-2 卫星影像。

传统做法需要在 ArcGIS Pro 或 QGIS 中手动操作数十步：下载数据、裁剪、设符号、排版、加经纬网、加比例尺……而这个工具把一切简化为：**选省市 → 点按钮 → 拿图**。

## 核心功能

- **三级区位图**：自动排版中国→省→城市三个尺度的地图，带连接指示
- **GEE 数据集成**：一键从 Google Earth Engine 下载 DEM / 山体阴影 / Sentinel-2
- **多引擎渲染**：支持 QGIS (PyQGIS) / ArcGIS Pro / Cartopy 三种出图引擎
- **出图即论文**：经纬网、比例尺、指北针、图例、标题一步到位，300 DPI 高清输出
- **自定义研究区**：除了中国省市选择，还可上传自定义 SHP 文件
- **智能缓存**：已下载的 GEE 数据自动缓存，不重复下载

## 快速开始

### 环境准备

```bash
# 1. 安装 QGIS (免费)
#    Windows: https://qgis.org/download/
#    安装时选择 OSGeo4W 完整安装

# 2. 创建 conda 环境
conda create -n rmw python=3.11
conda activate rmw

# 3. 安装依赖
pip install -e ".[dev]"

# 4. 配置 GEE (首次需要)
#    参见 docs/gee_setup_guide.md

# 5. 启动
python -m src.main
```

### GEE 配置

首次使用需要完成 Google Earth Engine 认证，详见 [GEE 配置教程](docs/gee_setup_guide.md)。

## 出图效果

> 截图待补充

## 项目状态

🚧 **Alpha 阶段** — 核心功能开发中

## 贡献

欢迎贡献代码、报告 Bug、改进文档！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

GPL-3.0 — 与 QGIS 许可证兼容。
