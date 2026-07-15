import anyio
import httpx
import pytest

from conftest import app_client
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.settings import get_settings
from platform_app.services.preprocess_service import PreprocessService
from platform_app.services.remix_service import RemixService
from tests.fakes.algorithm_service_fakes import FakeGenerationAdapter, FakePreprocessAdapter


async def _prepare_role_video_with_asr(client, role_name="角色A", video_name="demo.mp4"):
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


async def _prepare_two_roles_with_asr(client):
    role_a, video_a = await _prepare_role_video_with_asr(client, "角色A", "role-a.mp4")
    role_b, video_b = await _prepare_role_video_with_asr(client, "角色B", "role-b.mp4")
    return (role_a, video_a), (role_b, video_b)


@pytest.mark.anyio
async def test_preprocess_jobs_include_asr_records(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    async with app_client() as client:
        role, video = await _prepare_role_video_with_asr(client)

        response = await client.get("/api/remix/preprocess-jobs")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"items", "asr_records"}
    assert payload["items"] == []
    assert payload["asr_records"][0]["video_id"] == video["id"]
    assert payload["asr_records"][0]["role_name"] == role["name"]
    assert payload["asr_records"][0]["asr_status"] == "success"


@pytest.mark.anyio
async def test_preprocess_jobs_and_tasks_support_role_filter(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.remix as remix_api
    from platform_app.settings import get_settings

    class UniqueFakePreprocessAdapter(FakePreprocessAdapter):
        def build_segments(self, *, video_id: str, video_path: str, asr_full_text: str, asr_segments: list[dict]):
            del video_path, asr_full_text
            output_dir = self.base_dir / "generated" / "preprocess" / video_id / "segments"
            output_dir.mkdir(parents=True, exist_ok=True)
            results = []
            for index, segment in enumerate(asr_segments, start=1):
                segment_id = f"{video_id}-segment-{index}"
                clip_path = output_dir / f"{segment_id}.mp4"
                clip_path.write_bytes(b"clip")
                results.append(
                    {
                        "segment_id": segment_id,
                        "start_sec": segment["start_sec"],
                        "end_sec": segment["end_sec"],
                        "duration_sec": segment["end_sec"] - segment["start_sec"],
                        "asr_text": segment["text"],
                        "segment_file_path": str(clip_path.resolve()),
                    }
                )
            return results

    preprocess_adapter = UniqueFakePreprocessAdapter(tmp_path / "work")
    generation_adapter = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")

    def fake_build_preprocess_service():
        settings = get_settings()
        return PreprocessService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            work_dir=settings.work_dir,
            preprocess_adapter=preprocess_adapter,
        )

    def fake_build_remix_service(preprocess_service):
        settings = get_settings()
        return RemixService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            preprocess_service=preprocess_service,
            generation_adapter=generation_adapter,
        )

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)

    async with app_client() as client:
        (role_a, video_a), (role_b, video_b) = await _prepare_two_roles_with_asr(client)

        for video in (video_a, video_b):
            response = await client.post("/api/remix/preprocess", json={"video_id": video["id"]})
            assert response.status_code == 200

        task_payload = {
            "source_video_id": video_a["id"],
            "prompt_text": "商品卖点",
            "product_doc_text": "",
            "target_count": 1,
            "is_max_mode": False,
            "aspect_mode": "default",
            "resolution": "720p",
            "subtitle_enabled": True,
        }
        for role in (role_a, role_b):
            task_response = await client.post(
                "/api/remix/tasks",
                json={**task_payload, "role_id": role["id"], "source_video_id": video_a["id"] if role is role_a else video_b["id"]},
            )
            assert task_response.status_code == 200

        filtered_jobs = await client.get(f"/api/remix/preprocess-jobs?role_id={role_a['id']}")
        assert filtered_jobs.status_code == 200
        filtered_payload = filtered_jobs.json()
        assert filtered_payload["items"]
        assert {item["role_id"] for item in filtered_payload["items"]} == {role_a["id"]}
        assert filtered_payload["asr_records"]
        assert {record["role_id"] for record in filtered_payload["asr_records"]} == {role_a["id"]}

        unfiltered_jobs = await client.get("/api/remix/preprocess-jobs")
        assert unfiltered_jobs.status_code == 200
        unfiltered_payload = unfiltered_jobs.json()
        assert unfiltered_payload["items"]
        assert {record["role_id"] for record in unfiltered_payload["asr_records"]} == {
            role_a["id"],
            role_b["id"],
        }

        filtered_tasks = await client.get(f"/api/remix/tasks?role_id={role_b['id']}")
        assert filtered_tasks.status_code == 200
        assert filtered_tasks.json()["items"]
        assert {item["role_id"] for item in filtered_tasks.json()["items"]} == {role_b["id"]}

        all_tasks = await client.get("/api/remix/tasks")
        assert all_tasks.status_code == 200
        assert {item["role_id"] for item in all_tasks.json()["items"]} == {
            role_a["id"],
            role_b["id"],
        }


@pytest.mark.anyio
async def test_remix_task_list_includes_smart_clip_projects(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    async with app_client() as client:
        role, video = await _prepare_role_video_with_asr(client)
        project = SmartClipRepository(get_settings().database_path).create_project(
            role_id=role["id"],
            source_video_id=video["id"],
            source_video_title=video["title"],
            status="exporting",
            stage="exporting",
        )
        SmartClipRepository(get_settings().database_path).update_project_progress(
            project["id"],
            stage="exporting",
            total_asr_segments=9,
            kept_sales_segments=5,
            candidate_clip_count=3,
            export_total_count=3,
            export_current_index=2,
            export_completed_count=1,
        )

        response = await client.get("/api/remix/tasks", params={"role_id": role["id"]})

    assert response.status_code == 200
    items = response.json()["items"]
    smart_clip_item = next(item for item in items if item.get("task_type") == "smart_clip")
    assert smart_clip_item["project_id"] == project["id"]
    assert smart_clip_item["source_video_id"] == video["id"]
    assert smart_clip_item["source_video_title"] == video["title"]
    assert smart_clip_item["progress_summary"] == "共 3 个候选切片，正在导出第 2 个"


@pytest.mark.anyio
async def test_remix_detail_uses_threadpool_for_blocking_work(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.remix as remix_api

    class StubPreprocessService:
        pass

    class StubRemixService:
        def get_task_detail(self, task_id: str):
            return {"task": {"id": task_id, "status": "running"}, "items": []}

    called = {}

    def fake_build_preprocess_service():
        return StubPreprocessService()

    def fake_build_remix_service(preprocess_service):
        assert isinstance(preprocess_service, StubPreprocessService)
        return StubRemixService()

    async def fake_run_in_threadpool(func, *args, **kwargs):
        called["func_name"] = getattr(func, "__name__", repr(func))
        called["args"] = args
        called["kwargs"] = kwargs
        return func(*args, **kwargs)

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)
    monkeypatch.setattr(remix_api, "run_in_threadpool", fake_run_in_threadpool)

    async with app_client() as client:
        response = await client.get("/api/remix/tasks/task-threadpool")

    assert response.status_code == 200
    assert response.json()["task"]["id"] == "task-threadpool"
    assert called["func_name"] == "get_task_detail"
    assert called["args"] == ("task-threadpool",)


@pytest.mark.anyio
async def test_remix_task_list_uses_service_to_refresh_real_status(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.remix as remix_api

    class StubPreprocessService:
        pass

    class StubRemixService:
        def list_tasks(self):
            return [
                {
                    "id": "task-real-status",
                    "role_id": "role-1",
                    "source_video_id": "video-1",
                    "status": "failed",
                    "error_message": "预处理未产出可用混剪片段",
                }
            ]

    called = {}

    def fake_build_preprocess_service():
        return StubPreprocessService()

    def fake_build_remix_service(preprocess_service):
        assert isinstance(preprocess_service, StubPreprocessService)
        return StubRemixService()

    async def fake_run_in_threadpool(func, *args, **kwargs):
        called["func_name"] = getattr(func, "__name__", repr(func))
        return func(*args, **kwargs)

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)
    monkeypatch.setattr(remix_api, "run_in_threadpool", fake_run_in_threadpool)

    async with app_client() as client:
        response = await client.get("/api/remix/tasks")

    assert response.status_code == 200
    assert called["func_name"] == "list_tasks"
    assert response.json()["items"][0]["status"] == "failed"
    assert response.json()["items"][0]["error_message"] == "预处理未产出可用混剪片段"


@pytest.mark.anyio
async def test_phase2_remix_endpoints_support_minimal_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.remix as remix_api
    from platform_app.settings import get_settings
    preprocess_adapter = FakePreprocessAdapter(tmp_path / "work")
    generation_adapter = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")

    def fake_build_preprocess_service():
        settings = get_settings()
        return PreprocessService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            work_dir=settings.work_dir,
            preprocess_adapter=preprocess_adapter,
        )

    def fake_build_remix_service(preprocess_service):
        settings = get_settings()
        return RemixService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            preprocess_service=preprocess_service,
            generation_adapter=generation_adapter,
        )

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)

    async with app_client() as client:
        role, video = await _prepare_role_video_with_asr(client)

        listed = await client.get(f"/api/roles/{role['id']}/remix/videos")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["id"] == video["id"]

        preprocess = await client.post("/api/remix/preprocess", json={"video_id": video["id"]})
        assert preprocess.status_code == 200
        preprocess_payload = preprocess.json()
        assert preprocess_payload["job"]["status"] in {"success", "running"}

        task_response = await client.post(
            "/api/remix/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "prompt_text": "商品卖点",
                "product_doc_text": "",
                "target_count": 1,
                "is_max_mode": False,
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert task_response.status_code == 200
        task = task_response.json()
        assert task["id"]

        task_status = task["status"]
        for _ in range(20):
            task_list = await client.get("/api/remix/tasks")
            assert task_list.status_code == 200
            assert task_list.json()["items"]
            task_status = task_list.json()["items"][0]["status"]
            if task_status in {"running", "success", "partial_success"}:
                break
            await anyio.sleep(0.05)
        assert task_status in {"running", "success", "partial_success"}

        detail_status = ""
        detail = None
        for _ in range(20):
            detail = await client.get(f"/api/remix/tasks/{task['id']}")
            assert detail.status_code == 200
            detail_status = detail.json()["task"]["status"]
            if detail_status in {"success", "partial_success", "running", "ready"} and detail.json()["items"]:
                break
            await anyio.sleep(0.05)
        assert detail is not None
        assert detail_status in {"success", "partial_success", "running", "ready"}
        assert detail.json()["items"]
        assert detail.json()["items"][0]["comfy_prompt_id"]

        polled = await client.post(f"/api/remix/tasks/{task['id']}/poll")
        assert polled.status_code == 200
        assert polled.json()["items"][0]["status"] in {"video_generating", "success", "failed"}

        cancelled_job = await client.post(
            f"/api/remix/preprocess-jobs/{preprocess_payload['job']['id']}/cancel"
        )
        assert cancelled_job.status_code == 200
        assert cancelled_job.json()["status"] in {"cancelled", "success"}

        cancelled_task = await client.post(f"/api/remix/tasks/{task['id']}/cancel")
        assert cancelled_task.status_code == 200
        assert cancelled_task.json()["status"] in {"cancelled", "success"}


@pytest.mark.anyio
async def test_create_remix_task_can_enter_pending_preprocess_before_background_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))

    import platform_app.api.remix as remix_api
    from platform_app.settings import get_settings
    preprocess_adapter = FakePreprocessAdapter(tmp_path / "work")
    generation_adapter = FakeGenerationAdapter(tmp_path / "temp", tmp_path / "generated")

    def fake_build_preprocess_service():
        settings = get_settings()
        return PreprocessService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            work_dir=settings.work_dir,
            preprocess_adapter=preprocess_adapter,
        )

    def fake_build_remix_service(preprocess_service):
        settings = get_settings()
        return RemixService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            preprocess_service=preprocess_service,
            generation_adapter=generation_adapter,
        )

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)

    async with app_client() as client:
        role, video = await _prepare_role_video_with_asr(client)

        task_response = await client.post(
            "/api/remix/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "prompt_text": "商品卖点",
                "product_doc_text": "",
                "target_count": 1,
                "is_max_mode": False,
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )

        assert task_response.status_code == 200
        assert task_response.json()["status"] == "pending_preprocess"


@pytest.mark.anyio
async def test_phase2_remix_endpoints_support_service_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_ASR_MODE", "mock")
    monkeypatch.setenv("BS_MEDIA_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("BS_MEDIA_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("BS_MEDIA_GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("BS_MEDIA_TTS_MODE", "service")
    monkeypatch.setenv("BS_MEDIA_COMFY_MODE", "service")

    import platform_app.api.remix as remix_api
    from platform_app.settings import get_settings
    from platform_app.services.remix_generation_adapter import RemixGenerationAdapter

    preprocess_adapter = FakePreprocessAdapter(tmp_path / "work")
    comfy_polls: dict[str, int] = {}

    def tts_handler(request: httpx.Request) -> httpx.Response:
        payload = request.read().decode("utf-8")
        item_id = "unknown"
        if "\"output_path\":" in payload:
            item_id = payload.split(".wav", 1)[0].rsplit("/", 1)[-1]
        audio_path = tmp_path / "temp" / "remix" / "task" / f"{item_id}.wav"
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
            prompt_id = f"prompt-{len(comfy_polls) + 1}"
            comfy_polls[prompt_id] = 0
            return httpx.Response(200, json={"status": "submitted", "prompt_id": prompt_id})
        prompt_id = request.url.path.rsplit("/", 1)[-1]
        comfy_polls[prompt_id] = comfy_polls.get(prompt_id, 0) + 1
        if comfy_polls[prompt_id] == 1:
            return httpx.Response(200, json={"status": "pending"})
        output_path = tmp_path / "generated" / "remix" / "task" / f"{prompt_id}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"video")
        return httpx.Response(
            200,
            json={"status": "success", "output_video_url": str(output_path.resolve())},
        )

    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._get_tts_adapter",
        lambda: __import__("platform_app.services.tts_adapter", fromlist=["TtsAdapter"]).TtsAdapter(
            service_base_url="http://tts.local",
            transport=httpx.MockTransport(tts_handler),
        ),
    )
    monkeypatch.setattr(
        "phase2_algorithms.remix_pipeline._get_comfy_client",
        lambda: __import__("platform_app.services.algorithm_http_client", fromlist=["AlgorithmHttpClient"]).AlgorithmHttpClient(
            base_url="http://comfy.local",
            service_name="视频生成",
            transport=httpx.MockTransport(comfy_handler),
        ),
    )

    def fake_build_preprocess_service():
        settings = get_settings()
        return PreprocessService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            work_dir=settings.work_dir,
            preprocess_adapter=preprocess_adapter,
        )

    def fake_build_remix_service(preprocess_service):
        settings = get_settings()
        return RemixService(
            db_path=settings.database_path,
            temp_dir=settings.temp_dir,
            generated_dir=settings.generated_dir,
            preprocess_service=preprocess_service,
            generation_adapter=RemixGenerationAdapter(
                temp_dir=settings.temp_dir,
                generated_dir=settings.generated_dir,
            ),
        )

    monkeypatch.setattr(remix_api, "build_preprocess_service", fake_build_preprocess_service)
    monkeypatch.setattr(remix_api, "build_remix_service", fake_build_remix_service)

    async with app_client() as client:
        role, video = await _prepare_role_video_with_asr(client)

        task_response = await client.post(
            "/api/remix/tasks",
            json={
                "role_id": role["id"],
                "source_video_id": video["id"],
                "prompt_text": "商品卖点",
                "product_doc_text": "",
                "target_count": 1,
                "is_max_mode": False,
                "aspect_mode": "default",
                "resolution": "720p",
                "subtitle_enabled": True,
            },
        )
        assert task_response.status_code == 200
        task = task_response.json()

        for _ in range(20):
            detail = await client.get(f"/api/remix/tasks/{task['id']}")
            payload = detail.json()
            if payload["items"] and payload["items"][0]["status"] in {"video_generating", "success"}:
                break
            await anyio.sleep(0.05)

        polled = await client.post(f"/api/remix/tasks/{task['id']}/poll")
        assert polled.status_code == 200
        item = polled.json()["items"][0]
        assert item["status"] in {"tts_generating", "video_generating", "success", "failed"}

        final_detail = await client.get(f"/api/remix/tasks/{task['id']}")
        final_item = final_detail.json()["items"][0]
        assert final_item["status"] in {"tts_generating", "video_generating", "success", "failed"}
