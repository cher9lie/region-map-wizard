# 贡献指南

感谢你对 Region Map Wizard 项目的兴趣！

## 开发环境搭建

```bash
git clone https://github.com/region-map-wizard/region-map-wizard.git
cd region-map-wizard
conda create -n rmw-dev python=3.11
conda activate rmw-dev
pip install -e ".[dev,cartopy]"
pre-commit install
```

如需测试 QGIS 引擎，需安装 QGIS 3.34+ 并配置 PyQGIS 环境。

## 代码规范

- Python 3.10+ 语法，使用 type hints
- 遵循 PEP 8，使用 `ruff` 格式化
- 路径操作使用 `pathlib.Path`
- 所有文件操作使用 UTF-8
- 变量名和注释用英文，用户可见文本用中文
- 提交前运行: `ruff check src/ tests/` 和 `pytest`

## 提交规范

提交信息格式:
```
<type>(<scope>): <description>

feat(gee): add Sentinel-2 download support
fix(renderer): fix grid interval calculation
docs: update GEE setup guide
test: add boundary_manager tests
refactor(core): extract cache logic
```

## Pull Request 流程

1. Fork 项目
2. 创建功能分支: `git checkout -b feat/my-feature`
3. 编写代码和测试
4. 确保 `pytest` 通过
5. 提交 PR，描述改动内容

## 目录说明

```
src/core/       — 核心业务逻辑 (不依赖 GUI)
src/gui/        — PyQt5 界面
src/renderers/  — 渲染引擎 (可插拔)
src/data/       — 内置数据文件
tests/          — 测试
docs/           — 文档
```
