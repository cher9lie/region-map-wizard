"""Custom exceptions for Region Map Wizard, keyed to SPEC error codes."""


class RMWError(Exception):
    """Base exception for all RMW errors."""

    code: str = "E000"

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


# ── GEE errors ────────────────────────────────────────────────────────────────

class GEEAuthFailedError(RMWError):
    code = "E001"

    def __init__(self, detail: str = ""):
        super().__init__("请先完成 Google Earth Engine 认证", detail)


class GEEDownloadFailedError(RMWError):
    code = "E002"

    def __init__(self, detail: str = ""):
        super().__init__("数据下载失败，请检查网络连接和 GEE 项目配置", detail)


class GEEQuotaExceededError(RMWError):
    code = "E003"

    def __init__(self, detail: str = ""):
        super().__init__("GEE 计算配额已超限，请稍后重试", detail)


# ── Renderer errors ────────────────────────────────────────────────────────────

class RendererNotAvailableError(RMWError):
    code = "E010"

    def __init__(self, renderer: str = "", detail: str = ""):
        msg = f"未检测到 {renderer} 安装，请安装后选择该引擎" if renderer else \
              "未检测到 QGIS 安装，请安装 QGIS 或选择其他引擎"
        super().__init__(msg, detail)


class RenderFailedError(RMWError):
    code = "E011"

    def __init__(self, detail: str = ""):
        super().__init__(f"制图过程出错: {detail}", detail)


# ── Boundary / data errors ─────────────────────────────────────────────────────

class BoundaryNotFoundError(RMWError):
    code = "E020"

    def __init__(self, adcode: str = "", detail: str = ""):
        msg = f"未找到行政区 {adcode} 的边界数据" if adcode else "未找到该行政区的边界数据"
        super().__init__(msg, detail)


class InvalidSHPError(RMWError):
    code = "E021"

    def __init__(self, detail: str = ""):
        super().__init__("上传的 SHP 文件无法读取或投影不明", detail)


# ── I/O errors ─────────────────────────────────────────────────────────────────

class IOError(RMWError):  # noqa: A001
    code = "E030"

    def __init__(self, detail: str = ""):
        super().__init__(f"文件操作失败: {detail}", detail)


class CacheError(RMWError):
    code = "E031"

    def __init__(self, detail: str = ""):
        super().__init__("缓存目录不可写", detail)
