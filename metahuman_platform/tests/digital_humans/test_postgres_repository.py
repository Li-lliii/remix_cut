import os
import uuid

import pytest

from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanGenerationTaskRepository,
    DigitalHumanProfileRepository,
    DigitalHumanRepository,
)


@pytest.mark.integration
def test_digital_human_repositories_can_use_postgres():
    database_url = os.environ.get("BS_MEDIA_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("set BS_MEDIA_TEST_POSTGRES_URL to run PostgreSQL integration test")

    suffix = uuid.uuid4().hex[:8]
    human = DigitalHumanRepository(database_url).create(
        name=f"测试数字人-{suffix}",
        avatar_type="real",
        gender="",
        status="training_pending",
    )
    profile = DigitalHumanProfileRepository(database_url).create(
        digital_human_id=human["id"],
        department="测试部门",
        organization="",
        speaker_name="",
        tags=["测试"],
        style="",
        description="",
        metadata={"source": "pytest"},
    )
    asset = DigitalHumanAssetRepository(database_url).create(
        digital_human_id=human["id"],
        asset_type="talking_video",
        filename="input.mp4",
        file_path=f"minio://bs-media/{human['id']}/input.mp4",
        content_type="video/mp4",
        storage_backend="minio",
        storage_key=f"{human['id']}/input.mp4",
        metadata={"source": "pytest"},
    )
    task = DigitalHumanGenerationTaskRepository(database_url).create(
        digital_human_id=human["id"],
        task_type="material_avatar_build",
        status="pending",
        prompt_text="测试",
        workflow_name="material_avatar_training",
    )

    assert profile["tags_json"] == ["测试"]
    assert asset["storage_backend"] == "minio"
    assert task["digital_human_id"] == human["id"]
    assert DigitalHumanRepository(database_url).get(human["id"])["name"].startswith("测试数字人-")

