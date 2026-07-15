from __future__ import annotations

from platform_app.infra.celery_app import celery_app
from platform_app.modules.digital_humans.workflows import DigitalHumanWorkflowRunner
from platform_app.settings import get_settings


@celery_app.task(name="digital_humans.run_generation_task")
def run_generation_task(task_id: str):
    settings = get_settings()
    db_ref = (
        settings.database_url
        if settings.database_url.startswith(("postgresql://", "postgresql+"))
        else settings.database_path
    )
    return DigitalHumanWorkflowRunner(db_path=db_ref).run_generation_task(task_id)
