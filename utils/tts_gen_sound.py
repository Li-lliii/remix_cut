'''
根据asr中获取原视频的字幕，生成聊天的文本，并且结合tts输出原声音说出的新话语

流程：
  1. 从原视频中随机截取约5秒含人声的参考音频（自动挑选人声最丰富的片段）；
  2. 对参考片段进行ASR识别，获取对应文字（用于日志展示和质量确认）；
  3. 调用 Qwen3-TTS 以参考音色合成新的话语语音；
  4. 输出WAV格式的新语音文件。

使用方式（命令行）:
    # 从已有话语文件读取（配合 gen_word.py 使用）
    python tts_gen_word.py video.mp4 --text-file output/gen_word_chat.txt

    # 直接传入话语文字
    python tts_gen_word.py video.mp4 --text "你好，今天来聊聊..."

    # 联动 gen_word.py 全流程：从ASR文字自动生成新话语后再合成
    python tts_gen_word.py video.mp4 --gen-from-asr output/results_qwen3.txt --mode chat
'''

import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple

PROJECT_ROOT    = Path(__file__).resolve().parent.parent


def _resolve_shared_asset(*parts: str) -> Path:
    local_path = PROJECT_ROOT.joinpath(*parts)
    if local_path.exists():
        return local_path

    project_root_str = str(PROJECT_ROOT)
    marker = "/.worktrees/"
    if marker in project_root_str:
        canonical_root = Path(project_root_str.split(marker, 1)[0]) / "function" / "remix_cut"
        fallback_path = canonical_root.joinpath(*parts)
        if fallback_path.exists():
            return fallback_path
    return local_path


QWEN3_TTS_ROOT = Path(
    os.environ.get("BS_MEDIA_QWEN3_TTS_ROOT", str(_resolve_shared_asset("Qwen3-TTS")))
).expanduser().resolve()
QWEN3_TTS_MODEL = Path(
    os.environ.get("BS_MEDIA_QWEN3_TTS_MODEL", str(QWEN3_TTS_ROOT / "Qwen3-TTS-12Hz-1.7B-Base"))
).expanduser().resolve()

print(f"[INFO] PROJECT_ROOT   : {PROJECT_ROOT}")
print(f"[INFO] QWEN3_TTS_MODEL: {QWEN3_TTS_MODEL}")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(QWEN3_TTS_ROOT))  # 使 qwen_tts 包可被导入

# ── 常量 ─────────────────────────────────────────────────────────────────────

DEFAULT_REF_DURATION = 5.0   # 参考音频时长（秒）
DEFAULT_SKIP_RATIO   = 0.05  # 跳过视频首尾各此比例，避免片头/片尾静音或背景音乐
DEFAULT_MAX_ATTEMPTS = 5     # 最多随机尝试次数，取 ASR 文字最长的片段作为参考

_tts_model = None


def _prepare_waveform_for_write(wav):
    import numpy as np

    if hasattr(wav, "detach"):
        wav = wav.detach().cpu().numpy()
    else:
        wav = np.asarray(wav)

    wav = np.asarray(wav, dtype=np.float32)
    wav = np.squeeze(wav)
    if wav.ndim > 2:
        raise RuntimeError(f"TTS 输出音频维度异常: shape={wav.shape}")
    if wav.ndim == 2 and wav.shape[0] < wav.shape[1]:
        wav = wav.T
    wav = np.nan_to_num(wav, nan=0.0, posinf=1.0, neginf=-1.0)
    return np.clip(wav, -1.0, 1.0)


def _write_wav_file(output_path: Path, wav, sample_rate: int) -> None:
    import wave
    import numpy as np
    import soundfile as sf

    waveform = _prepare_waveform_for_write(wav)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        sf.write(str(temp_path), waveform, int(sample_rate), format="WAV", subtype="PCM_16")
    except Exception as exc:
        print(f"[WARNING] soundfile write failed, fallback to wave: {exc}")
        pcm = (np.clip(waveform, -1.0, 1.0) * 32767.0).astype("<i2")
        channels = 1 if pcm.ndim == 1 else pcm.shape[1]
        with wave.open(str(temp_path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(int(sample_rate))
            handle.writeframes(pcm.tobytes())
    temp_path.replace(output_path)


# ── Qwen3-TTS 模型加载 ───────────────────────────────────────────────────────

def _get_tts_model(device: Optional[str] = None):
    '''
    懒加载 Qwen3-TTS 模型（全局单例），避免重复初始化。

    Args:
        device: 推理设备（如 "cuda:0"），None 表示自动选择（device_map="auto"）。

    Returns:
        Qwen3TTSModel 实例。
    '''
    global _tts_model
    if _tts_model is None:
        import torch
        from qwen_tts import Qwen3TTSModel
        device_map = device if device else "auto"
        print(f"[INFO] Loading Qwen3-TTS: {QWEN3_TTS_MODEL}  device={device_map}  dtype=bfloat16")
        _tts_model = Qwen3TTSModel.from_pretrained(
            str(QWEN3_TTS_MODEL),
            device_map=device_map,
            dtype=torch.bfloat16,
        )
    return _tts_model


# ── 视频工具函数 ──────────────────────────────────────────────────────────────

def _get_video_duration(video_path: Path) -> float:
    '''
    使用 ffprobe 获取视频时长（秒）。

    Args:
        video_path: 视频文件路径。

    Returns:
        时长（秒）的浮点数。

    Raises:
        RuntimeError: ffprobe 执行失败或输出无法解析时抛出。
    '''
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        raise RuntimeError(f"ffprobe 失败: {stderr}") from exc
    except ValueError as exc:
        raise RuntimeError(f"ffprobe 输出无法解析为时长: {exc}") from exc


def _extract_clip_to_wav(
    video_path: Path,
    start_time: float,
    duration: float,
    output_wav: str,
) -> None:
    '''
    使用 ffmpeg 从视频中截取指定时间段，转为16kHz单声道PCM WAV。

    Args:
        video_path:  源视频路径。
        start_time:  截取起始时间（秒）。
        duration:    截取时长（秒）。
        output_wav:  输出WAV文件路径。

    Raises:
        RuntimeError: ffmpeg 执行失败时抛出。
    '''
    command = [
        "ffmpeg", "-y",
        "-ss", f"{start_time:.3f}",
        "-i", str(video_path),
        "-t", f"{duration:.3f}",
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_wav,
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
        raise RuntimeError(
            f"ffmpeg 截取片段失败 (exit {exc.returncode}):\n{stderr}"
        ) from exc


# ── 参考片段选取 ──────────────────────────────────────────────────────────────

def extract_reference_clip(
    video_path: Path,
    output_dir: Path,
    ref_duration: float = DEFAULT_REF_DURATION,
    skip_ratio: float = DEFAULT_SKIP_RATIO,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    asr_device: str = "cuda:3",
    seed: Optional[int] = None,
    asr_text_resolver: Optional[Callable[[Path], str]] = None,
) -> Tuple[Path, str]:
    '''
    从视频中随机截取含人声的参考音频片段（约 ref_duration 秒）。

    选取策略：
      - 跳过视频首尾各 skip_ratio 比例的时间，规避片头/片尾的背景音乐或静音；
      - 在有效区间内随机尝试 max_attempts 次，取 ASR 识别文字最长的片段；
      - 最优片段另存为 WAV 文件，供 Qwen3-TTS 作为音色参考（ref_audio）。

    Args:
        video_path:    原视频文件路径。
        output_dir:    参考音频的保存目录。
        ref_duration:  参考片段时长（秒），默认5秒。
        skip_ratio:    跳过视频首尾的时间比例，默认5%。
        max_attempts:  最多随机尝试次数，默认5次。
        asr_device:    ASR 推理设备（如 "cuda:3"）。
        seed:          随机种子，None 表示每次真随机。

    Returns:
        (参考音频WAV路径, 对应ASR文字) 的元组。

    Raises:
        RuntimeError: 多次尝试后均未获取到有效语音时抛出。
    '''
    total_duration = _get_video_duration(video_path)
    print(f"[INFO] Video duration: {total_duration:.1f}s")

    rng = random.Random(seed)  # seed=None 时每次不同，保证参考片段多样

    # 计算有效截取区间（跳过首尾避免片头/片尾）
    margin       = total_duration * skip_ratio
    valid_start  = margin
    valid_end    = total_duration - margin - ref_duration
    if valid_end <= valid_start:
        # 视频较短时降级：直接从头开始
        valid_start = 0.0
        valid_end   = max(0.0, total_duration - ref_duration)

    if asr_text_resolver is None:
        import numpy as np
        import soundfile as sf

        from utils.asr_detect_word import _asr_segment, _get_asr_model

        asr_model = _get_asr_model(asr_device)

        def asr_text_resolver(clip_path: Path) -> str:
            audio_data, samplerate = sf.read(clip_path)
            audio_data = audio_data.astype(np.float32)
            return _asr_segment(asr_model, audio_data, samplerate)

    best_wav_path: Optional[str] = None
    best_asr_text: str           = ""
    tmp_paths = []

    for attempt in range(1, max_attempts + 1):
        start_sec = rng.uniform(valid_start, max(valid_start, valid_end))

        # 创建临时WAV文件
        tmp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp_file.name
        tmp_file.close()
        tmp_paths.append(tmp_path)

        # 截取视频片段
        try:
            _extract_clip_to_wav(video_path, start_sec, ref_duration, tmp_path)
        except RuntimeError as exc:
            print(f"[WARN] Attempt {attempt}: clip extraction failed: {exc}")
            continue

        # 对截取片段做 ASR，以人声文字量评估片段质量
        asr_text = asr_text_resolver(Path(tmp_path))

        preview  = asr_text[:60].replace("\n", " ")
        ellipsis = "..." if len(asr_text) > 60 else ""
        print(f"[INFO] Attempt {attempt}/{max_attempts}: "
              f"start={start_sec:.1f}s  "
              f"ASR({len(asr_text)} chars): '{preview}{ellipsis}'")

        # 取 ASR 文字最多的片段作为参考（人声最丰富）
        if len(asr_text) > len(best_asr_text):
            best_asr_text = asr_text
            best_wav_path = tmp_path

    # 清理非最优临时文件
    for path in tmp_paths:
        if path != best_wav_path:
            try:
                os.unlink(path)
            except OSError:
                pass

    if best_wav_path is None:
        raise RuntimeError(
            "多次尝试后未能从视频中提取到含有效人声的参考片段，"
            "请检查视频文件或调整 skip_ratio / max_attempts 参数。"
        )

    # 将最优临时文件移至输出目录，方便复用和检查
    output_dir.mkdir(parents=True, exist_ok=True)
    ref_output = output_dir / f"ref_{video_path.stem}.wav"
    shutil.move(best_wav_path, str(ref_output))

    print(f"[INFO] Reference clip saved : {ref_output}")
    print(f"[INFO] Reference ASR text   : {best_asr_text}")
    return ref_output, best_asr_text


# ── TTS 合成 ──────────────────────────────────────────────────────────────────

def synthesize_speech(
    reference_audio: Path,
    ref_text: str,
    text: str,
    output_path: Path,
    tts_device: Optional[str] = None,
) -> Path:
    '''
    调用 Qwen3-TTS，以参考音频的音色合成给定文字的语音。

    Args:
        reference_audio: 参考音频WAV文件路径（为 Qwen3-TTS 提供音色）。
        ref_text:        参考音频对应的ASR文字（Qwen3-TTS 音色克隆必需）。
        text:            需要合成的话语文字。
        output_path:     输出WAV文件路径。
        tts_device:      TTS推理设备，None 表示自动选择。

    Returns:
        输出WAV文件路径。
    '''
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tts = _get_tts_model(device=tts_device)

    preview      = text[:80].replace("\n", " ")
    ellipsis     = "..." if len(text) > 80 else ""
    ref_preview  = ref_text[:60].replace("\n", " ")
    ref_ellipsis = "..." if len(ref_text) > 60 else ""
    print(f"[INFO] Synthesizing speech ...")
    print(f"[INFO]   Reference audio : {reference_audio}")
    print(f"[INFO]   Reference text  : '{ref_preview}{ref_ellipsis}'")
    print(f"[INFO]   Output path     : {output_path}")
    print(f"[INFO]   Text ({len(text)} chars): '{preview}{ellipsis}'")

    wavs, sr = tts.generate_voice_clone(
        text=text,
        language="Chinese",
        ref_audio=str(reference_audio),
        ref_text=ref_text,
    )

    _write_wav_file(output_path, wavs[0], int(sr))

    print(f"[INFO] TTS complete. Output: {output_path}")
    return output_path


# ── 主函数 ───────────────────────────────────────────────────────────────────

def tts_from_video(
    video_path,
    new_text: str,
    output_path=None,
    ref_duration: float = DEFAULT_REF_DURATION,
    asr_device: str = "cuda:3",
    tts_device: Optional[str] = None,
    seed: Optional[int] = None,
    asr_text_resolver: Optional[Callable[[Path], str]] = None,
) -> Path:
    '''
    从原视频中提取音色参考，对新话语内容进行TTS语音合成（克隆原说话人音色）。

    完整流程：
      1. 从视频中随机截取约 ref_duration 秒的参考音频（自动挑选人声最丰富的片段）；
      2. 对参考片段进行ASR识别，输出对应文字（用于日志展示和质量确认）；
      3. 调用 Qwen3-TTS，以参考音色合成 new_text 的语音；
      4. 将WAV文件保存到 output_path。

    Args:
        video_path:    原视频文件路径（用于提取音色参考）。
        new_text:      需要合成的新话语文字（由 gen_word.py 生成）。
        output_path:   输出WAV路径，默认保存至 output/<视频名>_tts.wav。
        ref_duration:  参考音频时长（秒），默认5秒。
        asr_device:    ASR推理设备（用于评估参考片段的人声质量）。
        tts_device:    Qwen3-TTS推理设备，None 表示自动选择。
        seed:          随机种子，None 表示每次真随机（参考片段选取位置不同）。
        asr_text_resolver: 可选的参考音频识别器。提供后，参考片段评分通过外部回调完成。

    Returns:
        生成的语音WAV文件路径。

    Raises:
        FileNotFoundError: 视频文件不存在时抛出。
        RuntimeError:      参考片段提取或TTS合成失败时抛出。
    '''
    video_path = Path(video_path).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    output_dir = PROJECT_ROOT / "output"
    if output_path is None:
        output_path = output_dir / f"{video_path.stem}_tts.wav"
    output_path = Path(output_path)

    # ── Step 1: 从原视频提取音色参考片段 ────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[STEP 1] Extracting reference audio from: {video_path}")
    print(f"{'='*60}")
    ref_audio, ref_text = extract_reference_clip(
        video_path,
        output_dir=output_dir / "refs",
        ref_duration=ref_duration,
        asr_device=asr_device,
        seed=seed,
        asr_text_resolver=asr_text_resolver,
    )

    
    # ── Step 2: 以参考音色合成新话语 ────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"[STEP 2] Synthesizing new speech with Qwen3-TTS")
    print(f"{'='*60}")
    result = synthesize_speech(
        reference_audio=ref_audio,
        ref_text=ref_text,
        text=new_text,
        output_path=output_path,
        tts_device=tts_device,
    )

    print(f"\n{'='*60}")
    print(f"[DONE] Output: {result}")
    print(f"{'='*60}")
    return result


def warmup_tts_model(device: Optional[str] = None):
    return _get_tts_model(device=device)


def is_tts_model_loaded() -> bool:
    return _tts_model is not None


# ── 入口 ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="从原视频克隆音色，对新话语内容进行TTS语音合成",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "video",
        help="原视频路径（用于提取音色参考）",
    )

    # 话语来源（三选一）
    text_group = parser.add_mutually_exclusive_group()
    text_group.add_argument(
        "--text", metavar="TEXT",
        help="直接传入需要合成的话语文字",
    )
    text_group.add_argument(
        "--text-file", metavar="PATH",
        help="从文本文件读取需要合成的话语（如 gen_word.py 的输出文件）",
    )
    text_group.add_argument(
        "--gen-from-asr", metavar="ASR_FILE",
        help="指定ASR文字文件路径，联动 gen_word.py 自动生成话语后再合成",
    )

    parser.add_argument(
        "--mode", choices=["chat", "sell"], default="chat",
        help="联动 gen_word.py 时的生成模式（仅 --gen-from-asr 有效）",
    )
    parser.add_argument(
        "--output", metavar="PATH",
        help="输出WAV文件路径（默认: output/<视频名>_tts.wav）",
    )
    parser.add_argument(
        "--ref-duration", type=float, default=DEFAULT_REF_DURATION,
        help="参考音频时长（秒）",
    )
    parser.add_argument(
        "--ref-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS,
        help="参考片段随机尝试次数，取人声最丰富的一段",
    )
    parser.add_argument(
        "--asr-device", default="cuda:3",
        help="ASR推理设备（参考片段质量评估用）",
    )
    parser.add_argument(
        "--tts-device", default="cuda:3",
        help="Qwen3-TTS推理设备（默认自动选择）",
    )
    args = parser.parse_args()

    # ── 获取待合成文字 ───────────────────────────────────────────────────
    if args.text:
        new_text = args.text
        print(f"[INFO] 使用命令行传入的话语文字 ({len(new_text)} chars)")

    elif args.text_file:
        text_path = Path(args.text_file)
        if not text_path.exists():
            print(f"[ERROR] 话语文件不存在: {text_path}", file=sys.stderr)
            sys.exit(1)
        new_text = text_path.read_text(encoding="utf-8").strip()
        print(f"[INFO] 从文件读取话语: {text_path} ({len(new_text)} chars)")

    elif args.gen_from_asr:
        asr_path = Path(args.gen_from_asr)
        if not asr_path.exists():
            print(f"[ERROR] ASR文字文件不存在: {asr_path}", file=sys.stderr)
            sys.exit(1)
        asr_text = asr_path.read_text(encoding="utf-8")
        print(f"[INFO] 从ASR文件生成话语: {asr_path} ({len(asr_text)} chars), "
              f"mode={args.mode}")
        from utils.gen_word import generate_speech_text
        new_text = generate_speech_text(asr_text, mode=args.mode)

    else:
        print(
            "[ERROR] 请通过 --text / --text-file / --gen-from-asr 其中之一指定合成内容",
            file=sys.stderr,
        )
        parser.print_help()
        sys.exit(1)

    # ── 执行 TTS ─────────────────────────────────────────────────────────
    output_path = Path(args.output) if args.output else None
    result_path = tts_from_video(
        video_path=args.video,
        new_text=new_text,
        output_path=output_path,
        ref_duration=args.ref_duration,
        asr_device=args.asr_device,
        tts_device=args.tts_device,
    )

    print(f"\n[INFO] 合成完成！语音文件已保存至: {result_path}")
