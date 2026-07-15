from __future__ import annotations

from platform_app.infra.redis import RedisProgressStore
from platform_app.settings import get_settings


class DigitalHumanProgress:
    def __init__(self, *, store: RedisProgressStore | None = None):
        settings = get_settings()
        self.store = store or RedisProgressStore(redis_url=settings.redis_url, prefix="bs_media:digital_humans")

    def set(self, task_id: str, *, progress: int, stage: str, message: str = "", extra: dict | None = None):
        return self.store.set_progress(task_id, progress=progress, stage=stage, message=message, extra=extra)

    def get(self, task_id: str) -> dict:
        return self.store.get_progress(task_id)

