from __future__ import annotations

from pathlib import Path
import re
from typing import Any


_CUDA_DEVICE_PATTERN = re.compile(r"^cuda:(\d+)$", re.IGNORECASE)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config.yaml"


def _load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else _default_config_path()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    config: dict[str, Any] = {}
    current_section: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not raw_line.startswith((" ", "\t")) and line.endswith(":"):
            current_section = line[:-1].strip()
            config[current_section] = {}
            continue

        if current_section is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        section = config.get(current_section)
        if isinstance(section, dict):
            section[key] = value

    return config


def _normalize_physical_device(device: Any, *, default: str) -> tuple[str, str]:
    raw = str(device if device is not None else default).strip()
    if not raw:
        raw = default

    if raw.lower() == "cpu":
        return "", "cpu"

    matched = _CUDA_DEVICE_PATTERN.match(raw)
    if matched:
        return matched.group(1), "cuda:0"

    if raw.isdigit():
        return raw, "cuda:0"

    raise ValueError(f"不支持的显卡配置: {raw}")


def load_algorithm_gpu_bindings(config_path: str | Path | None = None) -> dict[str, dict[str, str]]:
    config = _load_config(config_path)
    asr_config = config.get("asr") or {}
    tts_config = config.get("tts") or {}

    asr_visible_devices, asr_runtime_device = _normalize_physical_device(
        asr_config.get("device"),
        default="cuda:0",
    )
    tts_visible_devices, tts_runtime_device = _normalize_physical_device(
        tts_config.get("device"),
        default="cuda:0",
    )

    return {
        "asr": {
            "visible_devices": asr_visible_devices,
            "runtime_device": asr_runtime_device,
        },
        "tts": {
            "visible_devices": tts_visible_devices,
            "runtime_device": tts_runtime_device,
        },
    }


def load_algorithm_service_env(config_path: str | Path | None = None) -> dict[str, str]:
    bindings = load_algorithm_gpu_bindings(config_path)
    return {
        "ASR_GPU": bindings["asr"]["visible_devices"],
        "ASR_DEVICE": bindings["asr"]["runtime_device"],
        "TTS_GPU": bindings["tts"]["visible_devices"],
        "TTS_ASR_DEVICE": bindings["tts"]["runtime_device"],
        "TTS_DEVICE": bindings["tts"]["runtime_device"],
    }
