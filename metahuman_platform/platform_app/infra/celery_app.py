from __future__ import annotations

from platform_app.settings import get_settings


class MissingCeleryApp:
    def task(self, *decorator_args, **decorator_kwargs):
        del decorator_args, decorator_kwargs

        def decorate(func):
            func.delay = self._missing_delay  # type: ignore[attr-defined]
            func.apply_async = self._missing_delay  # type: ignore[attr-defined]
            return func

        return decorate

    def send_task(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("celery 依赖未安装，无法投递 Celery 任务")

    def _missing_delay(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("celery 依赖未安装，无法投递 Celery 任务")


def create_celery_app():
    settings = get_settings()
    try:
        from celery import Celery  # type: ignore
    except ModuleNotFoundError as exc:
        del exc
        return MissingCeleryApp()

    app = Celery(
        "bs_media",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["platform_app.modules.digital_humans.tasks"],
    )
    app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"])
    return app


celery_app = create_celery_app()
