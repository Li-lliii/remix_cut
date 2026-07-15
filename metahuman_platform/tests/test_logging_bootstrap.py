from pathlib import Path


def test_platform_start_script_redirects_stdout_and_stderr():
    script = (Path(__file__).resolve().parents[1] / "start.sh").read_text(encoding="utf-8")

    # 必须禁用 Python 输出缓冲，否则日志可能不实时落盘。
    assert "PYTHONUNBUFFERED=1" in script

    # 必须明确写入平台日志文件，避免日志只在控制台而文件为空。
    assert "logs/platform" in script
    assert "uvicorn-7028.log" in script
    assert "2>&1" in script


def test_algorithm_start_script_uses_unbuffered_or_live_output():
    script = (Path(__file__).resolve().parents[2] / "scripts" / "start_algorithm_services.sh").read_text(
        encoding="utf-8"
    )

    # conda run 默认可能捕获/缓冲输出，必须禁用捕获以便实时落盘。
    assert "conda run" in script
    assert "--no-capture-output" in script
    assert "PYTHONUNBUFFERED=1" in script


def test_server_initializes_logging_on_startup():
    server = (Path(__file__).resolve().parents[1] / "server.py").read_text(encoding="utf-8")

    # 平台入口应在启动早期初始化统一日志。
    assert "platform_app.logging_config" in server
    assert "setup_logging" in server
