from __future__ import annotations

import json
from typing import Any


class RedisProgressStore:
    def __init__(self, *, redis_url: str, prefix: str = "bs_media:progress"):
        self.redis_url = redis_url
        self.prefix = prefix.rstrip(":")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import redis  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError("redis 依赖未安装，无法使用 Redis 进度存储") from exc
        self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def _key(self, task_id: str) -> str:
        return f"{self.prefix}:{task_id}"

    def set_progress(self, task_id: str, *, progress: int, stage: str, message: str = "", extra: dict | None = None):
        payload: dict[str, Any] = {
            "progress": max(0, min(int(progress), 100)),
            "stage": stage,
            "message": message,
            "extra": extra or {},
        }
        self._get_client().set(self._key(task_id), json.dumps(payload, ensure_ascii=False))
        return payload

    def get_progress(self, task_id: str) -> dict:
        raw = self._get_client().get(self._key(task_id))
        if not raw:
            return {"progress": 0, "stage": "pending", "message": "", "extra": {}}
        return json.loads(raw)

