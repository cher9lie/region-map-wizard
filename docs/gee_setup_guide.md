# Google Earth Engine 配置教程

本文档指导你完成 GEE 账号注册、Cloud Project 创建和 Python API 认证。

---

## 1. 注册 Google Earth Engine 账号

1. 访问 https://earthengine.google.com/
2. 点击右上角 **Sign Up** / **Get started**
3. 用 Google 账号登录，填写申请表（选 **非商业/学术研究** 用途）
4. 等待审核邮件（通常几分钟到 1 天）

> **提示**：如果你有高校邮箱（.edu），审核更快。

---

## 2. 创建 Google Cloud Project

GEE Python API v1.4+ 需要绑定一个 Cloud Project。

1. 访问 https://console.cloud.google.com/
2. 点击顶部的项目选择器 → **新建项目**
3. 填写项目名（例如 `rmw-project`），记住 **Project ID**
4. 在项目中启用 **Earth Engine API**：
   - 左侧菜单 → **API 和服务** → **库**
   - 搜索 `Earth Engine API` → 点击 **启用**

---

## 3. 首次 Python API 认证

### 方法 A：在工具 GUI 中认证（推荐）

1. 启动 Region Map Wizard：`python -m src.main`
2. 点击 **GEE 认证设置…** 按钮
3. 填入你的 Cloud Project ID（步骤 2 中记录的）
4. 点击 **开始认证（会弹出浏览器）**
5. 在浏览器中选择你的 Google 账号并授权
6. 授权完成后回到工具，状态显示"认证成功"

### 方法 B：命令行认证

```bash
python -c "import ee; ee.Authenticate(); ee.Initialize(project='YOUR_PROJECT_ID')"
```

浏览器会自动打开，完成 OAuth 授权后凭证保存在 `~/.config/earthengine/`，后续自动复用。

---

## 4. 验证配置

运行以下代码验证 GEE 连接正常：

```python
import ee
ee.Initialize(project="YOUR_PROJECT_ID")
image = ee.Image("USGS/SRTMGL1_003")
print(image.getInfo()["id"])  # 应输出 USGS/SRTMGL1_003
```

---

## 5. 常见问题

### Q: 认证时浏览器没有弹出？
- 确保系统有默认浏览器
- 尝试命令行：`earthengine authenticate`（需安装 earthengine-api）

### Q: 报错 "quota exceeded"？
- GEE 免费账号有每日下载配额限制
- 工具支持本地缓存，已下载的数据不会重复请求
- 如需大批量下载，可申请 GEE 商业账号

### Q: 报错 "project not found"？
- 检查 Project ID 是否正确（不是项目名，是 ID）
- 确认 Earth Engine API 已在该项目中启用

### Q: 网络连接问题（中国大陆）？
- 需要通过 VPN 访问 Google 服务
- 认证和数据下载都需要稳定的网络连接

---

## 6. 数据集说明

| 数据集 | GEE Asset ID | 分辨率 | 更新频率 |
|--------|------------|--------|---------|
| SRTM DEM | `USGS/SRTMGL1_003` | 30m | 静态（2000年） |
| Sentinel-2 | `COPERNICUS/S2_SR_HARMONIZED` | 10m | 每5天 |

工具默认下载缩小分辨率（DEM 90m，Sentinel-2 100m），足够区位图使用且下载速度快。
