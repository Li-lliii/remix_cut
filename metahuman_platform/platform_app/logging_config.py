import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class _ContextFilter(logging.Filter):
    def __init__(self, *, service_name: str):
        super().__init__()
        self._service_name = str(service_name)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        # 保证 formatter 需要的字段始终存在，避免缺字段导致格式化报错。
        if not hasattr(record, "service_name"):
            record.service_name = self._service_name
        for key in ("task_id", "item_id", "prompt_id", "stage"):
            if not hasattr(record, key):
                setattr(record, key, "-")
        return True


def setup_logging(*, service_name: str, log_file: str | Path, level: str | int = "INFO") -> None:
    """配置统一的文件日志 + 控制台日志。

    约定：
    - 默认同时保留文件输出与控制台输出
    - 强制补齐 service_name/task_id/item_id/prompt_id/stage，避免缺字段导致格式化异常
    - 单进程内可重复调用，重复调用不会重复挂载 handler
    """

    root = logging.getLogger()
    if getattr(root, "_bs_media_logging_configured", False):
        return

    resolved_level = level
    if isinstance(level, str):
        resolved_level = logging.getLevelName(level.upper())
    root.setLevel(resolved_level)
    root.handlers.clear()

    log_path = Path(log_file).expanduser().resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = (
        "%(asctime)s %(levelname)s "
        "service=%(service_name)s pid=%(process)d thread=%(threadName)s "
        "task_id=%(task_id)s item_id=%(item_id)s prompt_id=%(prompt_id)s stage=%(stage)s "
        "%(name)s: %(message)s"
    )
    formatter = logging.Formatter(fmt=fmt)
    context_filter = _ContextFilter(service_name=str(service_name))

    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)

    console_handler = logging.StreamHandler(stream=sys.stderr)
    console_handler.setLevel(resolved_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root._bs_media_logging_configured = True
