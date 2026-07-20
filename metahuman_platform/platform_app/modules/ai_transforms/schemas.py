from __future__ import annotations

from pydantic import BaseModel, Field


ENABLED_OPERATIONS = {"replace_background"}
SUPPORTED_OPERATIONS = {
    "replace_background",
    "replace_clothes",
    "replace_avatar",
    "replace_speech",
    "replace_product",
}

CAPABILITIES = [
    {
        "operation": "replace_background",
        "label": "换背景",
        "enabled": True,
        "required_inputs": ["background_image"],
        "optional_inputs": [],
    },
    {
        "operation": "replace_clothes",
        "label": "换服装",
        "enabled": False,
        "required_inputs": ["clothes_image"],
        "optional_inputs": [],
    },
    {
        "operation": "replace_avatar",
        "label": "换数字人",
        "enabled": False,
        "required_inputs": ["avatar_reference"],
        "optional_inputs": [],
    },
    {
        "operation": "replace_speech",
        "label": "换口播",
        "enabled": False,
        "required_inputs": [],
        "optional_inputs": ["speech_audio", "speech_text"],
    },
    {
        "operation": "replace_product",
        "label": "换产品",
        "enabled": False,
        "required_inputs": ["product_image"],
        "optional_inputs": [],
    },
]


class AiTransformCreatePayload(BaseModel):
    role_id: str = Field(min_length=1)
    source_video_id: str = Field(min_length=1)
    operations: list[str] = Field(default_factory=lambda: ["replace_background"], min_length=1)
    input_asset_keys: dict[str, str] = Field(default_factory=dict)
    params: dict = Field(default_factory=dict)


class AiTransformSubmitPayload(BaseModel):
    task_id: str = Field(min_length=1)
