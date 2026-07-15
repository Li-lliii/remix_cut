"""
平台服务入口。

Phase 1 重点提供：
1. 角色与视频管理 API
2. 上传即触发 ASR
3. 平台静态页面壳子
"""

from contextlib import asynccontextmanager
from pathlib import Path
import os
import logging

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from platform_app.db import init_db
from platform_app.logging_config import setup_logging
from platform_app.modules.routers import get_api_routers
from platform_app.settings import get_settings


def error_payload(code: str, message: str, *, details=None):
    return {"error": {"code": code, "message": message, "details": details}}


def _init_platform_logging() -> None:
    # 尽量早初始化，避免应用启动早期日志丢失。
    root = Path(__file__).resolve().parents[2]  # .../function
    default_log_file = root / "logs" / "platform" / "uvicorn-7028.log"
    log_file = Path(os.environ.get("BS_MEDIA_PLATFORM_LOG_FILE", str(default_log_file)))
    level = os.environ.get("BS_MEDIA_LOG_LEVEL", "INFO")
    setup_logging(service_name="platform", log_file=log_file, level=level)


_init_platform_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    init_db(settings.database_path)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="智媒数字人平台",
        description="测试阶段",
        version="1.0.0",
        lifespan=lifespan,
    )
    logging.getLogger(__name__).info("平台服务启动初始化完成")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in get_api_routers():
        app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload("http_error", detail),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_payload("validation_error", "请求参数校验失败", details=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=error_payload("internal_error", str(exc)),
        )

    @app.get("/api/health")
    async def health_check():
        settings = get_settings()
        return {
            "status": "ok",
            "database": str(settings.database_path),
            "database_url": settings.database_url,
            "digital_human_database_backend": "postgresql"
            if settings.database_url.startswith(("postgresql://", "postgresql+"))
            else "sqlite",
            "asr_mode": settings.asr_mode,
            "tts_mode": settings.tts_mode,
            "comfy_mode": settings.comfy_mode,
        }

    @app.get("/")
    async def index():
        settings = get_settings()
        return HTMLResponse((settings.static_dir / "index.html").read_text(encoding="utf-8"))

    @app.get("/app/{path:path}")
    async def app_shell(path: str):
        settings = get_settings()
        return HTMLResponse((settings.static_dir / "index.html").read_text(encoding="utf-8"))

    static_dir = get_settings().static_dir
    assets_dir = static_dir / "platform"
    if assets_dir.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/static/platform", StaticFiles(directory=assets_dir), name="platform-static")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
