from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ComfyJobStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): dict(value) for key, value in payload.items() if isinstance(value, dict)}

    def _write(self, payload: dict[str, dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_job(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = self._read()
        prompt_id = str(record["prompt_id"])
        payload[prompt_id] = dict(record)
        self._write(payload)
        return payload[prompt_id]

    def get_job(self, prompt_id: str) -> dict[str, Any] | None:
        return self._read().get(str(prompt_id))

    def update_job(self, prompt_id: str, **updates: Any) -> dict[str, Any]:
        payload = self._read()
        record = dict(payload.get(str(prompt_id)) or {})
        if not record:
            raise KeyError(prompt_id)
        record.update(updates)
        payload[str(prompt_id)] = record
        self._write(payload)
        return record
