from pathlib import Path

from platform_app.services.gpu_binding import load_algorithm_gpu_bindings


def test_load_algorithm_gpu_bindings_maps_physical_gpu_to_service_runtime_device(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
asr:
  device: "cuda:3"
tts:
  device: "2"
""".strip(),
        encoding="utf-8",
    )

    bindings = load_algorithm_gpu_bindings(config_path)

    assert bindings["asr"]["visible_devices"] == "3"
    assert bindings["asr"]["runtime_device"] == "cuda:0"
    assert bindings["tts"]["visible_devices"] == "2"
    assert bindings["tts"]["runtime_device"] == "cuda:0"


def test_load_algorithm_gpu_bindings_keeps_cpu_without_visible_devices(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
asr:
  device: "cpu"
tts:
  device: "cpu"
""".strip(),
        encoding="utf-8",
    )

    bindings = load_algorithm_gpu_bindings(config_path)

    assert bindings["asr"]["visible_devices"] == ""
    assert bindings["asr"]["runtime_device"] == "cpu"
    assert bindings["tts"]["visible_devices"] == ""
    assert bindings["tts"]["runtime_device"] == "cpu"
