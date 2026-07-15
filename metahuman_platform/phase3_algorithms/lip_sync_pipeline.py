from pathlib import Path

from . import duration_estimator
from . import media_generation
from . import script_generation


def generate_script_candidates(
    *,
    base_video_path: str,
    base_video_asr_text: str,
    prompt_text: str,
    product_doc_text: str,
    count: int,
):
    '''
    生成候选话术
    '''
    return script_generation.build_script_candidates(
        base_video_path=base_video_path,
        base_video_asr_text=base_video_asr_text,
        prompt_text=prompt_text,
        product_doc_text=product_doc_text,
        count=count,
        duration_callback=validate_script_tts_duration_with_context,
    )


def regenerate_script_candidate(
    *,
    base_video_path: str,
    base_video_asr_text: str,
    prompt_text: str,
    product_doc_text: str,
    source_script_text: str,
):
    '''
    重新生成话术
    '''
    return script_generation.regenerate_script(
        base_video_path=base_video_path,
        base_video_asr_text=base_video_asr_text,
        prompt_text=prompt_text,
        product_doc_text=product_doc_text,
        source_script_text=source_script_text,
        duration_callback=validate_script_tts_duration_with_context,
    )


def validate_script_tts_duration(*, base_video_path: str, script_text: str):
    duration_sec = duration_estimator._get_video_duration_sec(base_video_path)
    return duration_estimator.validate_duration_from_context(script_text, duration_sec, "")


def validate_script_tts_duration_with_context(
    *,
    base_video_duration_sec: float,
    base_video_asr_text: str,
    script_text: str,
):
    return duration_estimator.validate_duration_from_context(
        script_text,
        base_video_duration_sec,
        base_video_asr_text,
    )


def submit_lip_sync_generation(
    *,
    task_id: str,
    base_video_path: str,
    script_text: str,
    aspect_mode: str,
    resolution: str,
    subtitle_enabled: bool,
    temp_dir: str,
    output_dir: str,
):
    #生成 TTS 音频
    tts_path = media_generation.generate_tts_with_fallback(
        base_video_path=base_video_path,
        script_text=script_text,
        task_id=task_id,
        temp_dir=temp_dir,
    )
    #把基础视频 + TTS 音频提交给 ComfyUI 做对口型视频生成
    job_id = media_generation.submit_comfyui_job(
        task_id=task_id,
        base_video_path=base_video_path,
        tts_audio_path=tts_path,
        output_dir=output_dir,
        aspect_mode=aspect_mode,
        resolution=resolution,
        subtitle_enabled=subtitle_enabled,
    )
    if not job_id:
        raise RuntimeError("submit_lip_sync_generation 未返回有效 video_job_id")
    return {
        "final_script_text": script_text,
        "tts_audio_path": str(Path(tts_path).expanduser().resolve()),
        "video_job_id": job_id,
    }


def poll_lip_sync_generation(*, task_id: str, video_job_id: str):
    if not video_job_id:
        return {"status": "failed", "message": "缺少有效的视频生成任务ID"}
    result = media_generation.poll_comfyui_job(task_id=task_id, video_job_id=video_job_id)
    if result["status"] == "pending":
        return {"status": "pending"}
    if result["status"] == "success":
        output_path = Path(str(result["output_video_url"])).expanduser().resolve()
        if output_path.exists():
            return {
                "status": "success",
                "output_video_url": str(output_path),
            }
    return {"status": "failed", "message": "视频生成状态异常"}


def poll_lip_sync_generation_with_output_dir(
    *,
    task_id: str,
    video_job_id: str,
    output_dir: str,
):
    if not video_job_id:
        return {"status": "failed", "message": "缺少有效的视频生成任务ID"}
    result = media_generation.poll_comfyui_job(
        task_id=task_id,
        video_job_id=video_job_id,
        output_dir=output_dir,
    )
    if result["status"] == "pending":
        return {"status": "pending"}
    if result["status"] == "success":
        output_path = Path(str(result["output_video_url"])).expanduser().resolve()
        if output_path.exists():
            return {
                "status": "success",
                "output_video_url": str(output_path),
            }
    return {"status": "failed", "message": "视频生成状态异常"}
