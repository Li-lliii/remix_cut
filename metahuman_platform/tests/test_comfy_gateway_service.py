import importlib
import logging
import sys
import types

from fastapi.testclient import TestClient

from algorithm_services.comfy_gateway_service import (
    ComfyJobStore,
    _backend_ready,
    _poll_underlying_job,
    create_app,
)


def test_comfy_gateway_health_and_ready(monkeypatch, tmp_path):
    app = create_app(
        job_store=ComfyJobStore(tmp_path / "jobs.json"),
        submitter=lambda **kwargs: "prompt-1",
        poller=lambda **kwargs: {"status": "pending"},
        ready_checker=lambda: True,
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ready", "comfyui_reachable": True}


def test_comfy_gateway_persists_prompt_and_polls_without_output_dir(tmp_path, caplog):
    calls = []

    def submitter(**kwargs):
        calls.append(("submit", kwargs["output_dir"]))
        return "prompt-123"

    def poller(**kwargs):
        calls.append(("poll", kwargs["prompt_id"], kwargs["output_dir"]))
        if len([item for item in calls if item[0] == "poll"]) == 1:
            return {"status": "pending"}
        return {"status": "success", "output_video_url": f"{kwargs['output_dir']}/result.mp4"}

    store = ComfyJobStore(tmp_path / "jobs.json")
    app = create_app(job_store=store, submitter=submitter, poller=poller, ready_checker=lambda: True)

    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        submit = client.post(
            "/jobs",
            json={
                "video_path": "/abs/path/base.mp4",
                "audio_path": "/abs/path/base.wav",
                "output_dir": str(tmp_path / "final"),
                "task_type": "lip_sync",
                "task_id": "task-1",
            },
        )
        assert submit.status_code == 200
        assert submit.json() == {"status": "submitted", "prompt_id": "prompt-123"}

        first_poll = client.get("/jobs/prompt-123")
        assert first_poll.status_code == 200
        assert first_poll.json() == {"status": "pending"}

        second_poll = client.get("/jobs/prompt-123")
        assert second_poll.status_code == 200
        assert second_poll.json() == {
            "status": "success",
            "output_video_url": str((tmp_path / "final" / "result.mp4").resolve()),
        }

    assert any("stage=comfy_submit_start" in record.getMessage() for record in caplog.records)
    assert any("stage=comfy_submit_success" in record.getMessage() for record in caplog.records)
    assert any("stage=comfy_poll_pending" in record.getMessage() for record in caplog.records)
    assert any("stage=comfy_poll_success" in record.getMessage() for record in caplog.records)

    assert calls[0] == ("submit", str((tmp_path / "final").resolve()))
    assert calls[1][0] == "poll"
    assert calls[1][1] == "prompt-123"
    assert calls[1][2] == str((tmp_path / "final").resolve())
    assert store.get_job("prompt-123")["output_dir"] == str((tmp_path / "final").resolve())


def test_comfy_gateway_unknown_prompt_returns_404(tmp_path):
    app = create_app(job_store=ComfyJobStore(tmp_path / "jobs.json"), ready_checker=lambda: True)

    with TestClient(app) as client:
        response = client.get("/jobs/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "任务不存在"


def test_backend_ready_checks_underlying_comfy_server(monkeypatch):
    fake_module = types.ModuleType("utils.gen_video")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def check_health(self):
            return False

    fake_module.ComfyUIClient = FakeClient
    monkeypatch.setitem(sys.modules, "utils.gen_video", fake_module)
    gateway = importlib.import_module("algorithm_services.comfy_gateway_service")
    monkeypatch.setattr(gateway, "_load_comfy_config", lambda: {"server_address": "127.0.0.1:7030"})

    assert _backend_ready() is False


def test_poll_underlying_job_returns_pending_while_running(monkeypatch, tmp_path):
    fake_module = types.ModuleType("utils.gen_video")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_history(self, prompt_id):
            return {
                prompt_id: {
                    "status": {"status_str": "running"},
                    "outputs": {},
                }
            }

        def extract_output_video(self, task_data):
            return None

    fake_module.ComfyUIClient = FakeClient
    monkeypatch.setitem(sys.modules, "utils.gen_video", fake_module)
    gateway = importlib.import_module("algorithm_services.comfy_gateway_service")
    monkeypatch.setattr(
        gateway,
        "_load_comfy_config",
        lambda: {"server_address": "127.0.0.1:7030"},
    )

    result = _poll_underlying_job(prompt_id="prompt-1", output_dir=str(tmp_path / "final"))

    assert result == {"status": "pending"}


def test_poll_underlying_job_returns_success_when_output_exists(monkeypatch, tmp_path):
    fake_module = types.ModuleType("utils.gen_video")
    output_path = tmp_path / "result.mp4"
    output_path.write_bytes(b"video")

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def get_history(self, prompt_id):
            return {
                prompt_id: {
                    "status": {"status_str": "completed"},
                    "outputs": {},
                }
            }

        def extract_output_video(self, task_data):
            return str(output_path)

    fake_module.ComfyUIClient = FakeClient
    monkeypatch.setitem(sys.modules, "utils.gen_video", fake_module)
    gateway = importlib.import_module("algorithm_services.comfy_gateway_service")
    monkeypatch.setattr(
        gateway,
        "_load_comfy_config",
        lambda: {"server_address": "127.0.0.1:7030"},
    )

    result = _poll_underlying_job(prompt_id="prompt-2", output_dir=str(tmp_path / "final"))

    assert result == {"status": "success", "output_video_url": str(output_path.resolve())}
