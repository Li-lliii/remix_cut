from pydantic import BaseModel, Field


class DigitalHumanTaskView(BaseModel):
    id: str
    digital_human_id: str
    task_type: str
    status: str
    prompt_text: str = ""
    workflow_name: str = ""
    result_asset_ids_json: list[str] = Field(default_factory=list)
    error_message: str | None = None


class DigitalHumanCreateResponse(BaseModel):
    digital_human: dict
    profile: dict
    assets: list[dict]
    primary_asset: dict | None
    generation_task: dict


class DigitalHumanUploadFileSpec(BaseModel):
    field: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    content_type: str = "application/octet-stream"


class DigitalHumanObjectTaskCreatePayload(BaseModel):
    digital_human_id: str
    task_type: str = Field(min_length=1)
    workflow_name: str = Field(min_length=1)
    prompt_text: str = ""
    files: list[DigitalHumanUploadFileSpec] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


class DigitalHumanTaskSubmitPayload(BaseModel):
    task_id: str


class DigitalHumanEditTaskCreatePayload(BaseModel):
    source_video_filename: str = Field(min_length=1)
    source_video_content_type: str = "video/mp4"
    reference_filename: str = Field(min_length=1)
    reference_content_type: str = "image/png"
    prompt_text: str = ""
    params: dict = Field(default_factory=dict)
