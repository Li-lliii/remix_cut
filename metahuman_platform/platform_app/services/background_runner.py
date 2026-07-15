import logging
import threading


logger = logging.getLogger(__name__)


def _preview(value, *, limit: int = 120) -> str:
    text = repr(value)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def run_in_background(func, *args, **kwargs):
    """用守护线程执行后台任务，避免请求响应被 Starlette BackgroundTasks 绑定。"""

    def worker():
        try:
            func(*args, **kwargs)
        except Exception:
            arg_preview = [_preview(arg) for arg in args[:3]]
            kw_preview = {key: _preview(value) for key, value in list(kwargs.items())[:5]}
            # 这里必须带上调用上下文，便于定位是哪一个 task 卡住/失败了。
            logger.exception(
                "后台任务执行失败: func=%s args=%s kwargs=%s",
                getattr(func, "__name__", repr(func)),
                arg_preview,
                kw_preview,
            )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread
