import logging
from pathlib import Path


def _reset_root_logger():
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    if hasattr(root, "_bs_media_logging_configured"):
        delattr(root, "_bs_media_logging_configured")


def test_setup_logging_writes_to_file_and_preserves_context_fields(tmp_path: Path):
    _reset_root_logger()

    from platform_app.logging_config import setup_logging

    log_file = tmp_path / "service.log"
    setup_logging(service_name="unit-test", log_file=log_file, level="INFO")

    logger = logging.getLogger("unit.test")
    logger.info(
        "hello",
        extra={
            "task_id": "t1",
            "item_id": "i1",
            "prompt_id": "p1",
            "stage": "poll_pending",
        },
    )

    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass

    content = log_file.read_text(encoding="utf-8")
    assert "unit-test" in content
    assert "task_id=t1" in content
    assert "item_id=i1" in content
    assert "prompt_id=p1" in content
    assert "stage=poll_pending" in content
    assert "hello" in content


def test_setup_logging_does_not_fail_when_context_missing(tmp_path: Path):
    _reset_root_logger()

    from platform_app.logging_config import setup_logging

    log_file = tmp_path / "service.log"
    setup_logging(service_name="unit-test", log_file=log_file, level="INFO")

    logger = logging.getLogger("unit.test")
    logger.info("no-context")

    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass

    content = log_file.read_text(encoding="utf-8")
    assert "unit-test" in content
    assert "task_id=-" in content
    assert "item_id=-" in content
    assert "prompt_id=-" in content
    assert "stage=-" in content
    assert "no-context" in content

