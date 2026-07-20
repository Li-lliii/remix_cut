import subprocess
from pathlib import Path

from .script_generation import _count_effective_chars


DEFAULT_CHARS_PER_SEC = 5.0


def _get_video_duration_sec(video_path: str) -> float:
    '''
    获取视频的长度
    '''
    path = Path(video_path).expanduser().resolve()
    if not path.exists():
        return 0.0
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return float((result.stdout or "").strip() or 0.0)
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def validate_duration_from_context(
    script_text: str,
    base_video_duration_sec: float,
    base_video_asr_text: str = "",
) -> dict:
    '''
    计算语音的时长
    '''
    script_chars = _count_effective_chars(script_text) # 计算有效字符
    if script_chars == 0:
        return {"estimated_tts_duration_sec": 0.0, "valid": True}

    chars_per_sec = DEFAULT_CHARS_PER_SEC
    asr_chars = _count_effective_chars(base_video_asr_text)
    if base_video_duration_sec > 0 and asr_chars > 0:
        estimated_chars_per_sec = asr_chars / base_video_duration_sec
        if 1.5 <= estimated_chars_per_sec <= 8.0:
            chars_per_sec = estimated_chars_per_sec
    duration_sec = round(script_chars / chars_per_sec, 1)
    return {
        "estimated_tts_duration_sec": duration_sec,
        "valid": duration_sec <= 30.0,
    }


def estimate_duration_from_context(
    script_text: str,
    base_video_duration_sec: float,
    base_video_asr_text: str = "",
) -> float:
    '''
    评估语音合成的时长
    '''
    return validate_duration_from_context(
        script_text=script_text,
        base_video_duration_sec=base_video_duration_sec,
        base_video_asr_text=base_video_asr_text,
    )["estimated_tts_duration_sec"]
