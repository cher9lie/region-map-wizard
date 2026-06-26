# 开发心得与 Bug 记录

记录本项目开发过程中踩过的坑、解决思路以及设计决策。按时间顺序排列，供后续维护参考。

---

## 1. PyInstaller 打包：GDAL DLL 无法加载

**现象**

打包后的 exe 运行时，调用 geopandas 制图会弹出：

```
The 'read_file' function requires the 'pyogrio' or 'fiona' package...
Importing pyogrio resulted in: GDAL DLL could not be found.
```

**根因**

pyogrio、rasterio、pyproj、shapely 等 GIS 包通过 delvewheel 机制加载 GDAL/GEOS/PROJ 的原生 DLL。delvewheel 在包被 import 时执行一个启动 patch，patch 里用 `os.path.isdir(__file__)` 找到旁边的 `*.libs/` 目录并调用 `os.add_dll_directory()`。

在 PyInstaller one-dir 模式下，Python 模块被打包进 `.pyz` 归档文件。从归档里 import 的模块，其 `__file__` 是一个虚拟路径，`os.path.isdir()` 返回 False，因此 `*.libs/` 目录从未被注册，DLL 加载失败。

**解决方案**

在任何 GIS 包被 import 之前，手动扫描 `sys._MEIPASS`（或 exe 旁的 `_internal/` 目录）里所有 `*.libs` 子目录，逐一调用 `os.add_dll_directory()` 并写入 `PATH`：

- `src/main.py` 入口点最开头调用 `_setup_bundled_dlls()`
- `hooks/rthook_gdal_dlls.py` PyInstaller runtime hook，在用户模块 import 前执行

两处冗余注册确保无论哪个 import 先触发都能找到 DLL。

---

## 2. PyInstaller 打包：`No module named 'pyogrio._geometry'`

**现象**

修复 DLL 问题后，错误变为：

```
Importing pyogrio resulted in: No module named 'pyogrio._geometry'
```

**根因**

PyInstaller 通过静态分析找到需要打包的模块。`pyogrio._geometry` 是 Cython 编译的 `.pyd` 文件，只在 `pyogrio.geopandas` 模块里被 import，而 `pyogrio.geopandas` 并不在 `hiddenimports` 列表里，因此整条依赖链断掉，`_geometry.cp312-win_amd64.pyd` 未被收录。

**解决方案**

在 `rmw.spec` 里做两件事：

1. `hiddenimports` 改用 `collect_submodules("pyogrio")` 自动枚举所有子模块（包括 `pyogrio.geopandas`）。
2. 在 `binaries` 里显式遍历 `venv/pyogrio/*.pyd` 并强制打包，防止 PyInstaller 静态分析遗漏任何 Cython 扩展：

```python
for pyd in (VENV_SP / "pyogrio").glob("*.pyd"):
    binaries.append((str(pyd), "pyogrio"))
```

---

## 3. PyInstaller 打包：`No module named 'unittest'`（matplotlib 间接依赖）

**现象**

为了减小体积，`rmw.spec` 的 `excludes` 列表里加了 `"unittest"`。结果 Cartopy 引擎报不可用。

**根因**

`matplotlib → pyparsing → pyparsing.testing → unittest`。`unittest` 被排除后，`pyparsing.testing` import 失败，导致 pyparsing 整体出错，进而 matplotlib 无法正常初始化，Cartopy 检测失败。

**解决方案**

把 `"unittest"` 从 `excludes` 列表中删除。`unittest` 虽然是标准库，但 PyInstaller 在 `noarchive=False` 模式下某些条件下会漏掉它。

---

## 4. 制图错误：`'adcode'` KeyError

**现象**

在 GUI 中选择城市并制图，日志显示"边界数据准备完成"后立即报错：

```
错误: 制图过程出错: 'adcode'
```

**根因**

原始设计中，pipeline 的 `_export_boundaries()` 会把单个省、单个城市分别导出为 GeoJSON 文件，再将这些路径写回 `config.province_boundary` / `config.city_boundary`。

渲染器的 `_read_layer()` 读取这些 GeoJSON 时：

- 渲染中国概览图需要**所有省份**，但 `province.geojson` 只有一个省
- 渲染省级图需要**省内所有城市**，但 `city.geojson` 只有一个城市
- 若 `_export_boundaries()` 内部因任何原因 exception，`except` 块写入空 GeoJSON（无任何列），渲染器后续 `gdf['adcode']` 就触发 `KeyError: 'adcode'`

**解决方案**

彻底去掉这一中间层：

- 渲染器的 `config.country_boundary` / `province_boundary` / `city_boundary` 直接指向原始 GPKG 文件，渲染器通过 `layer=` 参数和 `filter_col` 筛选所需数据
- GEE 几何体改为直接调用 `boundary_mgr.get_boundary(adcode, "city")` 获取，不依赖临时文件

这样既消除了 GeoJSON 中间层带来的列丢失风险，也使渲染器能正确读取完整的省份集合用于中国全图绘制。

---

## 5. 制图 OOM / 电脑卡死

**现象**

打开应用并制图（300 DPI），电脑整体卡死，随后所有应用关闭，像刚开机一样。

**根因**

为了让连接线精确对接各图框的真实角点（见 Bug #6），需要在画连线之前调用 `fig.canvas.draw()` 让 matplotlib 完成布局计算，之后再调用 `fig.savefig()`。

在 300 DPI 下，A4 画布 = 3508×2480 像素，`canvas.draw()` 渲染一次约消耗 35–100 MB 内存，再加上 GeoDataFrame、底图瓦片等，`draw` + `savefig` 两次渲染峰值内存可达 400–800 MB，极易触发系统 OOM Killer。

**解决方案**

`ax.get_position()` 返回的是 figure fraction（0–1 比例坐标），与 DPI **无关**。因此只需用低 DPI 触发布局计算，拿到位置后再恢复原始 DPI：

```python
_orig_dpi = fig.get_dpi()
fig.set_dpi(72)
fig.canvas.draw()          # ~2 MB 内存，仅用于布局计算
fig.set_dpi(_orig_dpi)
# 此后 ax.get_position() 返回正确的 figure fraction 坐标
self._add_zoom_connections(...)
fig.savefig(dpi=config.dpi)  # 正常 300 DPI 输出
```

内存峰值从 ~400 MB 降至 ~50 MB（约 8 倍改善）。

---

## 6. 连接线停在"半空中"，未触及图框角点

**现象**

从省图连向市县图的两条指示线，终点悬停在图框附近但没有正好贴到左边两个顶点。

**根因**

代码用硬编码的布局常量（`_AX_DETAIL = [100/297, 27/210, 182/297, 161/210]`）计算连线终点坐标。然而 cartopy 的 `GeoAxes` 在内部调用 `set_aspect('equal')`，matplotlib 会根据地图的经纬度跨度收缩坐标轴，使实际渲染的坐标轴比声明的矩形更小（居中对齐）。因此连线打到的是声明位置，而不是视觉上的图框角点。

**解决方案**

在 `fig.canvas.draw()` 之后（布局已最终确定），用 `ax.get_position()` 读取坐标轴的真实边界框：

```python
def _pos(ax):
    p = ax.get_position()
    return [p.x0, p.y0, p.width, p.height]

dp = _pos(ax_detail)
c_tl = (dp[0], dp[1] + dp[3])   # 市县图左上角（真实坐标）
c_bl = (dp[0], dp[1])            # 市县图左下角（真实坐标）
```

所有连线端点和 zoom box 的裁切边界均改用此方式获取，消除了与布局常量的偏差。

---

## 7. 引擎探测阻塞 GUI 约 15 秒

**现象**

应用启动后 15 秒内 GUI 完全无响应（无法点击、无法拖动窗口）。

**根因**

`_populate_engines()` 在主线程中同步调用三个引擎的 `check_available()`。其中 ArcGIS Pro 探测会执行 `subprocess.run(timeout=15)` 尝试调用 `arcpy`，整个过程阻塞 Qt 事件循环。

**解决方案**

将引擎探测移入后台 `QThread`：

```python
class _ProbeThread(QThread):
    done = pyqtSignal(list)
    def run(self):
        self.done.emit(_probe())   # _probe() 逐一检测三个引擎

self._probe_thread = _ProbeThread()
self._probe_thread.done.connect(_on_done)
self._probe_thread.start()
```

主线程先填入"检测中…"占位文本，探测完成后信号触发 `_on_done` 更新 ComboBox，GUI 始终保持响应。

---

## 8. 自定义 SHP 中文路径读取失败

**现象**

选择路径含中文的 SHP 文件（如 `D:\研究数据\边界.shp`）时，geopandas 报文件找不到。

**根因**

Windows 上 GDAL/pyogrio 在某些系统 ANSI 代码页下无法处理非 ASCII 路径。

**解决方案**

`read_shp_safe()` 检测路径是否含非 ASCII 字符，若含则将 `.shp`、`.shx`、`.dbf`、`.prj` 等所有伴随文件复制到系统临时目录（纯 ASCII 路径），从临时路径读取后清理：

```python
def read_shp_safe(path: Path) -> gpd.GeoDataFrame:
    try:
        path.as_posix().encode("ascii")
        return gpd.read_file(path)          # 纯 ASCII 路径，直接读
    except UnicodeEncodeError:
        pass
    tmpdir = Path(tempfile.mkdtemp(prefix="rmw_shp_"))
    try:
        for f in path.parent.iterdir():
            if f.stem.lower() == path.stem.lower():
                shutil.copy2(f, tmpdir / ("shp" + f.suffix.lower()))
        return gpd.read_file(tmpdir / "shp.shp")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
```

---

## 9. 学术斑马边框遮盖经纬线刻度

**现象**

地图边框的黑白交替条纹太粗，把图内的经纬线起始刻度遮住了一部分。

**解决方案**

将斑马框厚度系数 `s` 从 `0.013` 调整为 `0.008`（以图幅比例为单位），同时保持交替黑白条纹数量不变。

---

## 通用经验

- **PyInstaller + GIS 包**：所有 GIS 包（geopandas、pyogrio、rasterio、pyproj、shapely、cartopy）都用 delvewheel 封装 GDAL 系列 DLL，而 delvewheel 的 `__file__` 检测在 PYZ 归档下会失效。务必在入口点最开头、任何 GIS import 之前完成 DLL 路径注册。

- **Cartopy GeoAxes 的 aspect 收缩**：任何依赖图框精确位置的绘图逻辑（连线、标注框）都必须在 `fig.canvas.draw()` 或等效布局计算之后通过 `ax.get_position()` 获取坐标，不能用声明时的 rect 常量。

- **pipeline 与 renderer 的边界**：pipeline 负责数据获取与预处理，renderer 负责绘图。不要在 pipeline 里把数据序列化为临时文件再让 renderer 重新读取，这会引入不必要的 I/O、格式转换风险以及路径依赖。直接传递数据对象或原始文件路径。
