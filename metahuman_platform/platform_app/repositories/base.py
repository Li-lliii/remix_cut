import json
from datetime import datetime, timezone
from pathlib import Path

from platform_app.db import connect


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    if "tags" in data and isinstance(data["tags"], str):
        data["tags"] = json.loads(data["tags"])
    for field in (
        "tags_json",
        "metadata_json",
        "result_asset_ids_json",
        "input_asset_keys_json",
        "input_params_json",
        "params_json",
        "operations_json",
    ):
        if field in data and isinstance(data[field], str):
            data[field] = json.loads(data[field])
    for field in ("is_pinned", "is_max_mode", "subtitle_enabled", "is_selected", "is_edited"):
        if field in data:
            data[field] = bool(data.get(field, 0))
    return data


class BaseRepository:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connection(self):
        return connect(self.db_path)
