from __future__ import annotations

from platform_app.infra.celery_app import celery_app
from platform_app.modules.ai_transforms.workflows import AiTransformWorkflowRunner
from platform_app.settings import get_settings


@celery_app.task(name="ai_transforms.run_task")
def run_ai_transform_task(task_id: str):
    settings = get_settings()
    return AiTransformWorkflowRunner(db_path=settings.database_path).run_task(task_id)
