import anyio
import httpx
import pytest

from conftest import app_client
from platform_app.services.lip_sync_service import LipSyncService
from tests.fakes.algorithm_service_fakes import FakeLipSyncGenerationAdapter


async def _prepare_role_videos(client):
    role = (
        await client.post(
            "/api/roles",
            json={"name": "角色A", "description": "", "tags": []},
        )
    ).json()
    short_video = (
        await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("short.mp4", b"fake short video", "video/mp4")},
        )
    ).json()
    long_video = (
        await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("long.mp4", b"fake long video", "video/mp4")},
        )
    ).json()
    for video in (short_video, long_video):
        for _ in range(20):
            asr = (await client.get(f"/api/videos/{video['id']}/asr")).json()
            if asr["status"] == "success":
                break
            await anyio.sleep(0.05)
        else:
            raise AssertionError("上传后 ASR 未在预期时间内完成")
    return role, short_video, long_video


async def _prepare_role_video_with_asr(client, role_name, video_name):
    role = (
        await client.post(
            "/api/roles",
            json={"name": role_name, "description": "", "tags": []},
        )
    ).json()
    video = (
        await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": (video_name, b"fake video", "video/mp4")},
        )
    ).json()
    for _ in range(20):
        asr = (await client.get(f"/api/videos/{video['id']}/asr")).json()
        if asr["status"] == "success":
            break
        await anyio.sleep(0.05)
    else:
        raise AssertionError("上传后 ASR 未在预期时间内完成")
    return role, video


@pytest.mark.anyio
async def test_phase3_lip_sync_endpoints_support_minimal_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.lip_sync as lip_sync_api
    import platform_app.services.lip_sync_service as lip_sync_service_module
    from platform_app.settings import get_settings
    from platform_app.repositories.video_repository import VideoRepository

    generation_adapter = FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated")
    monkeypatch.setattr(lip_sync_service_module, "run_in_background", lambda func, *args, **kwargs: None)

    def fake_build_lip_sync_service():
        settings = get_settings()
        return LipSyncService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            generation_adapter=generation_adapter,
        )

    monkeypatch.setattr(lip_sync_api, "build_lip_sync_service", fake_build_lip_sync_service)

    async with app_client() as client:
        role, short_video, long_video = await _prepare_role_videos(client)

        settings = get_settings()
        video_repo = VideoRepository(settings.database_path)
        with video_repo.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (12.0, short_video["id"]),
            )
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (35.0, long_video["id"]),
            )
            connection.commit()

        listed = await client.get(f"/api/roles/{role['id']}/lip-sync/videos")
        assert listed.status_code == 200
        items = listed.json()["items"]
        by_id = {item["id"]: item for item in items}
        assert by_id[short_video["id"]]["selectable"] is True
        assert by_id[long_video["id"]]["selectable"] is False

        project_response = await client.post(
            "/api/lip-sync/projects",
            json={
                "role_id": role["id"],
                "base_video_id": short_video["id"],
                "prompt_text": "面膜补水",
                "product_doc_text": "补水商品文档",
            },
        )
        assert project_response.status_code == 200
        project = project_response.json()

        scripts_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/scripts/generate",
            json={"count": 3},
        )
        assert scripts_response.status_code == 200
        generated_payload = scripts_response.json()
        first_script = generated_payload["candidates"][0]
        assert len(generated_payload["candidates"]) == 3

        regenerate_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/scripts/{first_script['id']}/regenerate"
        )
        assert regenerate_response.status_code == 200
        regenerated_script = regenerate_response.json()
        assert regenerated_script["id"] == first_script["id"]

        project_detail = await client.get(f"/api/lip-sync/projects/{project['id']}")
        assert project_detail.status_code == 200
        refreshed_candidates = project_detail.json()["candidates"]
        assert len(refreshed_candidates) == 3
        assert refreshed_candidates[0]["id"] == first_script["id"]
        assert refreshed_candidates[0]["content"] == regenerated_script["content"]

        edited_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/scripts/{first_script['id']}/edit",
            json={"edited_content": "用户修改后的最终文案"},
        )
        assert edited_response.status_code == 200
        assert edited_response.json()["edited_content"] == "用户修改后的最终文案"

        selected_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/select-script",
            json={"script_id": first_script["id"]},
        )
        assert selected_response.status_code == 200
        assert selected_response.json()["project"]["status"] == "script_selected"

        task_response = await client.post(
            "/api/lip-sync/tasks",
            json={
                "project_id": project["id"],
                "selected_script_id": first_script["id"],
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert task_response.status_code == 200
        task = task_response.json()
        assert task["status"] in {"queued", "starting", "video_generating"}

        second_task_response = await client.post(
            "/api/lip-sync/tasks",
            json={
                "project_id": project["id"],
                "selected_script_id": first_script["id"],
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert second_task_response.status_code == 200
        second_task = second_task_response.json()
        assert second_task["status"] == "queued"

        listed_tasks = await client.get("/api/lip-sync/tasks")
        assert listed_tasks.status_code == 200
        assert listed_tasks.json()["items"]

        detail = await client.get(f"/api/lip-sync/tasks/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == task["status"]

        polled = await client.post(f"/api/lip-sync/tasks/{task['id']}/poll")
        assert polled.status_code == 200
        assert polled.json()["task"]["status"] == task["status"]

        cancelled = await client.post(f"/api/lip-sync/tasks/{task['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] in {"cancelled", "success"}


@pytest.mark.anyio
async def test_phase3_lip_sync_endpoints_support_service_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_TTS_MODE", "service")
    monkeypatch.setenv("BS_MEDIA_COMFY_MODE", "service")

    comfy_polls: dict[str, int] = {}
    import platform_app.api.lip_sync as lip_sync_api
    import platform_app.services.lip_sync_service as lip_sync_service_module
    monkeypatch.setattr(lip_sync_service_module, "run_in_background", lambda func, *args, **kwargs: None)

    def tts_handler(request: httpx.Request) -> httpx.Response:
        audio_path = tmp_path / "temp" / "lip_sync" / "task-1" / "tts" / "task-1.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"wav")
        return httpx.Response(
            200,
            json={
                "tts_audio_path": str(audio_path.resolve()),
                "voice_source": "clone",
                "fallback_used": False,
                "message": "ok",
            },
        )

    def comfy_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            prompt_id = f"job-{len(comfy_polls) + 1}"
            comfy_polls[prompt_id] = 0
            return httpx.Response(200, json={"status": "submitted", "prompt_id": prompt_id})
        prompt_id = request.url.path.rsplit("/", 1)[-1]
        comfy_polls[prompt_id] = comfy_polls.get(prompt_id, 0) + 1
        if comfy_polls[prompt_id] == 1:
            return httpx.Response(200, json={"status": "pending"})
        output_path = tmp_path / "generated" / "lip_sync" / "task-1" / "final" / f"{prompt_id}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        return httpx.Response(
            200,
            json={"status": "success", "output_video_url": str(output_path.resolve())},
        )

    monkeypatch.setattr(
        "phase3_algorithms.media_generation._get_tts_adapter",
        lambda: __import__("platform_app.services.tts_adapter", fromlist=["TtsAdapter"]).TtsAdapter(
            service_base_url="http://tts.local",
            transport=httpx.MockTransport(tts_handler),
        ),
    )
    monkeypatch.setattr(
        "phase3_algorithms.media_generation._get_comfy_client",
        lambda: __import__("platform_app.services.algorithm_http_client", fromlist=["AlgorithmHttpClient"]).AlgorithmHttpClient(
            base_url="http://comfy.local",
            service_name="视频生成",
            transport=httpx.MockTransport(comfy_handler),
        ),
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._call_generation_llm",
        lambda **kwargs: [
            "主打夜间补水修护，适合熬夜后快速舒缓。",
            "强调轻薄服帖和稳定保湿，适合换季使用。",
            "突出上脸舒服和补水体验，适合日常囤货。",
        ],
    )
    monkeypatch.setattr(
        "phase3_algorithms.script_generation._get_video_duration_sec",
        lambda path: 12.0,
    )
    monkeypatch.setattr(
        "phase3_algorithms.duration_estimator._get_video_duration_sec",
        lambda path: 12.0,
    )

    async with app_client() as client:
        role, short_video, long_video = await _prepare_role_videos(client)

        from platform_app.repositories.video_repository import VideoRepository
        from platform_app.settings import get_settings

        settings = get_settings()
        video_repo = VideoRepository(settings.database_path)
        with video_repo.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (12.0, short_video["id"]),
            )
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (35.0, long_video["id"]),
            )
            connection.commit()

        project_response = await client.post(
            "/api/lip-sync/projects",
            json={
                "role_id": role["id"],
                "base_video_id": short_video["id"],
                "prompt_text": "面膜补水",
                "product_doc_text": "补水商品文档",
            },
        )
        assert project_response.status_code == 200
        project = project_response.json()

        scripts_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/scripts/generate",
            json={"count": 3},
        )
        assert scripts_response.status_code == 200
        first_script = scripts_response.json()["candidates"][0]

        selected_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/select-script",
            json={"script_id": first_script["id"]},
        )
        assert selected_response.status_code == 200

        task_response = await client.post(
            "/api/lip-sync/tasks",
            json={
                "project_id": project["id"],
                "selected_script_id": first_script["id"],
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert task_response.status_code == 200
        task = task_response.json()
        assert task["status"] in {"queued", "starting", "video_generating"}

        detail = await client.get(f"/api/lip-sync/tasks/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == task["status"]

        polled = await client.post(f"/api/lip-sync/tasks/{task['id']}/poll")
        assert polled.status_code == 200
        assert polled.json()["task"]["status"] == task["status"]


@pytest.mark.anyio
async def test_lip_sync_task_detail_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    import platform_app.api.lip_sync as lip_sync_api
    import platform_app.services.lip_sync_service as lip_sync_service_module
    monkeypatch.setattr(lip_sync_service_module, "run_in_background", lambda func, *args, **kwargs: None)

    async with app_client() as client:
        role, short_video, _ = await _prepare_role_videos(client)

        from platform_app.repositories.video_repository import VideoRepository
        from platform_app.settings import get_settings

        settings = get_settings()
        video_repo = VideoRepository(settings.database_path)
        with video_repo.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (12.0, short_video["id"]),
            )
            connection.commit()

        project_response = await client.post(
            "/api/lip-sync/projects",
            json={
                "role_id": role["id"],
                "base_video_id": short_video["id"],
                "prompt_text": "面膜补水",
                "product_doc_text": "补水商品文档",
            },
        )
        assert project_response.status_code == 200
        project = project_response.json()

        scripts_response = await client.post(
            f"/api/lip-sync/projects/{project['id']}/scripts/generate",
            json={"count": 1},
        )
        assert scripts_response.status_code == 200
        script = scripts_response.json()["candidates"][0]

        await client.post(
            f"/api/lip-sync/projects/{project['id']}/select-script",
            json={"script_id": script["id"]},
        )

        task_response = await client.post(
            "/api/lip-sync/tasks",
            json={
                "project_id": project["id"],
                "selected_script_id": script["id"],
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert task_response.status_code == 200
        task = task_response.json()

        detail = await client.get(f"/api/lip-sync/tasks/{task['id']}")
        assert detail.status_code == 200
        assert detail.json()["task"]["status"] == task["status"]


@pytest.mark.anyio
async def test_lip_sync_tasks_support_role_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.lip_sync as lip_sync_api
    import platform_app.services.lip_sync_service as lip_sync_service_module
    from platform_app.repositories.video_repository import VideoRepository
    from platform_app.settings import get_settings

    generation_adapter = FakeLipSyncGenerationAdapter(tmp_path / "temp", tmp_path / "generated")

    def fake_build_lip_sync_service():
        settings = get_settings()
        return LipSyncService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            generation_adapter=generation_adapter,
        )

    monkeypatch.setattr(lip_sync_api, "build_lip_sync_service", fake_build_lip_sync_service)
    monkeypatch.setattr(lip_sync_service_module, "run_in_background", lambda func, *args, **kwargs: None)

    async with app_client() as client:
        role_a, video_a = await _prepare_role_video_with_asr(client, "角色A", "role-a.mp4")
        role_b, video_b = await _prepare_role_video_with_asr(client, "角色B", "role-b.mp4")

        settings = get_settings()
        video_repo = VideoRepository(settings.database_path)
        with video_repo.connection() as connection:
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (12.0, video_a["id"]),
            )
            connection.execute(
                "UPDATE role_videos SET duration_sec = ? WHERE id = ?",
                (12.0, video_b["id"]),
            )
            connection.commit()

        project_a = (
            await client.post(
                "/api/lip-sync/projects",
                json={
                    "role_id": role_a["id"],
                    "base_video_id": video_a["id"],
                    "prompt_text": "面膜补水",
                    "product_doc_text": "补水商品文档",
                },
            )
        ).json()
        project_b = (
            await client.post(
                "/api/lip-sync/projects",
                json={
                    "role_id": role_b["id"],
                    "base_video_id": video_b["id"],
                    "prompt_text": "面膜补水",
                    "product_doc_text": "补水商品文档",
                },
            )
        ).json()

        script_a = (
            await client.post(
                f"/api/lip-sync/projects/{project_a['id']}/scripts/generate",
                json={"count": 1},
            )
        ).json()["candidates"][0]
        script_b = (
            await client.post(
                f"/api/lip-sync/projects/{project_b['id']}/scripts/generate",
                json={"count": 1},
            )
        ).json()["candidates"][0]

        await client.post(
            f"/api/lip-sync/projects/{project_a['id']}/select-script",
            json={"script_id": script_a["id"]},
        )
        await client.post(
            f"/api/lip-sync/projects/{project_b['id']}/select-script",
            json={"script_id": script_b["id"]},
        )

        task_a = (
            await client.post(
                "/api/lip-sync/tasks",
                json={
                    "project_id": project_a["id"],
                    "selected_script_id": script_a["id"],
                    "aspect_mode": "default",
                    "resolution": "720p",
                    "subtitle_enabled": True,
                },
            )
        ).json()
        task_b = (
            await client.post(
                "/api/lip-sync/tasks",
                json={
                    "project_id": project_b["id"],
                    "selected_script_id": script_b["id"],
                    "aspect_mode": "default",
                    "resolution": "720p",
                    "subtitle_enabled": True,
                },
            )
        ).json()

        filtered_tasks = await client.get(f"/api/lip-sync/tasks?role_id={role_a['id']}")
        assert filtered_tasks.status_code == 200
        filtered_items = filtered_tasks.json()["items"]
        assert filtered_items
        assert {item["role_id"] for item in filtered_items} == {role_a["id"]}

        all_tasks = await client.get("/api/lip-sync/tasks")
        assert all_tasks.status_code == 200
        assert {item["role_id"] for item in all_tasks.json()["items"]} == {
            role_a["id"],
            role_b["id"],
        }

        assert {task_a["role_id"], task_b["role_id"]} == {role_a["id"], role_b["id"]}


@pytest.mark.anyio
async def test_lip_sync_detail_uses_threadpool_for_blocking_work(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")

    import platform_app.api.lip_sync as lip_sync_api

    class StubDetailService:
        def get_task_detail(self, task_id: str):
            return {"task": {"id": task_id, "status": "video_generating"}}

    called = {}

    async def fake_run_in_threadpool(func, *args, **kwargs):
        called["func_name"] = getattr(func, "__name__", repr(func))
        called["args"] = args
        called["kwargs"] = kwargs
        return func(*args, **kwargs)

    monkeypatch.setattr(lip_sync_api, "build_lip_sync_service", lambda: StubDetailService())
    monkeypatch.setattr(lip_sync_api, "run_in_threadpool", fake_run_in_threadpool)

    async with app_client() as client:
        response = await client.get("/api/lip-sync/tasks/task-threadpool")

    assert response.status_code == 200
    assert response.json()["task"]["id"] == "task-threadpool"
    assert called["func_name"] == "get_task_detail"
    assert called["args"] == ("task-threadpool",)
