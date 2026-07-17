from __future__ import annotations

from pydantic import BaseModel, Field


SUPPORTED_OPERATIONS = {"replace_background"}


class AiTransformCreatePayload(BaseModel):
    role_id: str = Field(min_length=1)
    source_video_id: str = Field(min_length=1)
    operations: list[str] = Field(default_factory=lambda: ["replace_background"], min_length=1)
    input_asset_keys: dict[str, str] = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)


class AiTransformSubmitPayload(BaseModel):
    task_id: str = Field(min_length=1)
