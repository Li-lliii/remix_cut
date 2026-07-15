import json
import logging
import shutil
from pathlib import Path

from phase2_algorithms.remix_pipeline import (
    build_sales_clip_candidates,
    classify_sales_segments_with_llm,
    concat_video_clips,
    cut_video_clip,
    resolve_bridge_segments,
)

from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.smart_clip_repository import SmartClipRepository
from platform_app.repositories.video_repository import VideoRepository


logger = logging.getLogger(__name__)
ACTIVE_SMART_CLIP_STATUSES = {"analyzing", "ready", "exporting"}


class SmartClipService:
    def __init__(self, *, db_path: Path, temp_dir: Path | None = None, generated_dir: Path | None = None):
        self.db_path = Path(db_path)
        self.temp_dir = Path(temp_dir) if temp_dir is not None else self.db_path.parent / "work" / "temp"
        self.generated_dir = Path(generated_dir) if generated_dir is not None else self.db_path.parent / "work" / "generated"
        self.video_repository = VideoRepository(self.db_path)
        self.asr_repository = AsrRepository(self.db_path)
        self.smart_clip_repository = SmartClipRepository(self.db_path)

    def _load_source_context(self, source_video_id: str):
        video = self.video_repository.get(source_video_id)
        if video is None:
            raise ValueError("源视频不存在")
        if str(video.get("asr_status") or "") != "success":
            raise ValueError("源视频的 ASR 尚未完成")
        asr_result = self.asr_repository.get_by_video(source_video_id)
        if asr_result is None:
            raise ValueError("源视频缺少 ASR 结果")
        return video, asr_result

    def _parse_json_field(self, value):
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            return value
        text = str(value).strip()
        if not text:
            return []
        return json.loads(text)

    def _enrich_candidate(self, candidate: dict):
        enriched = dict(candidate)
        enriched["segment_refs"] = self._parse_json_field(candidate.get("segment_refs_json")) or []
        enriched["source_time_ranges"] = self._parse_json_field(candidate.get("source_time_ranges_json")) or []
        return enriched

    def _build_project_detail(self, project: dict, *, allow_missing_source_video: bool = False):
        source_video = self.video_repository.get(project["source_video_id"])
        if source_video is None and not allow_missing_source_video:
            raise ValueError("源视频不存在")
        asr_result = self.asr_repository.get_by_video(project["source_video_id"])
        return {
            "project": project,
            "source_video": source_video,
            "asr_result": asr_result,
            "segments": self.smart_clip_repository.list_segments(project["id"]),
            "candidates": [
                self._enrich_candidate(candidate)
                for candidate in self.smart_clip_repository.list_candidates(project["id"])
            ],
        }

    def _build_failed_export_detail(self, *, project_id: str, error_message: str):
        self.smart_clip_repository.update_project_status(
            project_id,
            status="failed",
            stage="failed",
            error_message=error_message,
        )
        failed_project = self.smart_clip_repository.get_project(project_id)
        return self._build_project_detail(failed_project, allow_missing_source_video=True)

    def _project_export_dir(self, project_id: str) -> Path:
        return self.generated_dir / "smart_clips" / project_id

    def _project_temp_dir(self, project_id: str) -> Path:
        return self.temp_dir / "smart_clips" / project_id

    def _find_active_project(self, *, role_id: str, source_video_id: str):
        for project in self.smart_clip_repository.list_projects_by_role(role_id):
            if str(project.get("source_video_id") or "") != str(source_video_id):
                continue
            if str(project.get("status") or "") in ACTIVE_SMART_CLIP_STATUSES:
                return project
        return None

    def _reset_project_for_reprocess(self, *, project_id: str, source_video_id: str):
        shutil.rmtree(self._project_export_dir(project_id), ignore_errors=True)
        shutil.rmtree(self._project_temp_dir(project_id), ignore_errors=True)
        self.smart_clip_repository.replace_segments(
            project_id=project_id,
            source_video_id=source_video_id,
            segments=[],
        )
        self.smart_clip_repository.replace_candidates(
            project_id=project_id,
            candidates=[],
        )
        self.smart_clip_repository.update_project_progress(
            project_id,
            stage="classifying",
            total_asr_segments=0,
            kept_sales_segments=0,
            candidate_clip_count=0,
            export_total_count=0,
            export_completed_count=0,
            export_current_index=0,
        )
        return self.smart_clip_repository.update_project_status(
            project_id,
            status="analyzing",
            stage="classifying",
            error_message=None,
        )

    def _build_candidate_output_path(self, *, project_id: str, clip_index: int, candidate_id: str) -> Path:
        target_dir = self._project_export_dir(project_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f"clip-{clip_index:02d}-{candidate_id}.mp4"

    def _generate_candidate_previews(self, *, project: dict, candidates: list[dict], source_video_path: str):
        preview_total = len(candidates)
        preview_completed = 0
        self.smart_clip_repository.update_project_progress(
            project["id"],
            stage="generating_previews",
            export_total_count=preview_total,
            export_current_index=0,
            export_completed_count=0,
        )
        for current_index, candidate in enumerate(candidates, start=1):
            self.smart_clip_repository.update_project_progress(
                project["id"],
                stage="generating_previews",
                export_total_count=preview_total,
                export_current_index=current_index,
                export_completed_count=preview_completed,
            )
            try:
                preview_path = self._export_candidate_file(
                    project=project,
                    candidate=candidate,
                    source_video_path=source_video_path,
                )
                self.smart_clip_repository.set_candidate_preview_path(
                    candidate["id"],
                    output_video_path=preview_path,
                )
                preview_completed += 1
            except Exception as exc:
                self.smart_clip_repository.mark_candidate_failed(
                    candidate["id"],
                    error_message=str(exc),
                )
                raise
            self.smart_clip_repository.update_project_progress(
                project["id"],
                stage="generating_previews",
                export_total_count=preview_total,
                export_current_index=current_index,
                export_completed_count=preview_completed,
            )

    def _export_candidate_file(self, *, project: dict, candidate: dict, source_video_path: str) -> str:
        source_time_ranges = candidate.get("source_time_ranges") or []
        if not source_time_ranges:
            raise ValueError("候选切片缺少原始时间范围")

        output_path = self._build_candidate_output_path(
            project_id=project["id"],
            clip_index=int(candidate["clip_index"]),
            candidate_id=str(candidate["id"]),
        )
        if len(source_time_ranges) == 1:
            time_range = source_time_ranges[0]
            return cut_video_clip(
                video_path=source_video_path,
                start_sec=float(time_range["start_sec"]),
                end_sec=float(time_range["end_sec"]),
                output_path=str(output_path),
            )

        temp_dir = self._project_temp_dir(project["id"]) / str(candidate["id"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        clip_paths = []
        for part_index, time_range in enumerate(source_time_ranges, start=1):
            clip_path = temp_dir / f"part-{part_index:02d}.mp4"
            clip_paths.append(
                cut_video_clip(
                    video_path=source_video_path,
                    start_sec=float(time_range["start_sec"]),
                    end_sec=float(time_range["end_sec"]),
                    output_path=str(clip_path),
                )
            )
        return concat_video_clips(clip_paths=clip_paths, output_path=str(output_path))

    def create_project(self, *, role_id: str, source_video_id: str):
        video, _ = self._load_source_context(source_video_id)
        if str(video.get("role_id") or "") != str(role_id):
            raise ValueError("源视频不属于当前角色")
        project = self.smart_clip_repository.create_project(
            role_id=role_id,
            source_video_id=source_video_id,
            source_video_title=video["title"],
            status="analyzing",
            stage="classifying",
        )
        logger.info(
            "智能切片项目已创建: source_video_id=%s",
            source_video_id,
            extra={"task_id": project["id"], "stage": "smart_clip_project_created"},
        )
        return project

    def create_or_restart_project(self, *, role_id: str, source_video_id: str, force_recreate: bool = False):
        video, _ = self._load_source_context(source_video_id)
        if str(video.get("role_id") or "") != str(role_id):
            raise ValueError("源视频不属于当前角色")
        active_project = self._find_active_project(role_id=role_id, source_video_id=source_video_id)
        if active_project is not None:
            if not force_recreate:
                return active_project, False
            if str(active_project.get("status") or "") in {"analyzing", "exporting"}:
                raise ValueError("智能切片项目正在处理中，请稍后再试")
            restarted_project = self._reset_project_for_reprocess(
                project_id=active_project["id"],
                source_video_id=source_video_id,
            )
            logger.info(
                "智能切片项目已重置并准备重新分析: source_video_id=%s project_id=%s",
                source_video_id,
                active_project["id"],
                extra={"task_id": active_project["id"], "stage": "smart_clip_project_restarted"},
            )
            return restarted_project, True
        return self.create_project(role_id=role_id, source_video_id=source_video_id), True

    def process_project(self, project_id: str):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")

        self.smart_clip_repository.update_project_status(
            project_id,
            status="analyzing",
            stage="classifying",
            error_message=None,
        )
        try:
            source_video, asr_result = self._load_source_context(project["source_video_id"])
            asr_segments = list(asr_result.get("segments") or [])
            classified_segments = classify_sales_segments_with_llm(asr_segments=asr_segments)
            resolved_segments = resolve_bridge_segments(classified_segments)
            candidates = build_sales_clip_candidates(resolved_segments)

            stored_segments = self.smart_clip_repository.replace_segments(
                project_id=project_id,
                source_video_id=project["source_video_id"],
                segments=resolved_segments,
            )
            stored_candidates = self.smart_clip_repository.replace_candidates(
                project_id=project_id,
                candidates=[
                    {
                        "id": candidate.get("id"),
                        "clip_index": candidate["clip_index"],
                        "title": candidate.get("title") or f"切片 {candidate['clip_index']}",
                        "duration_sec": candidate["duration_sec"],
                        "segment_refs_json": json.dumps(candidate.get("segment_refs", []), ensure_ascii=False),
                        "source_time_ranges_json": json.dumps(candidate.get("source_time_ranges", []), ensure_ascii=False),
                        "preview_text": candidate.get("preview_text", ""),
                        "status": candidate.get("status", "active"),
                    }
                    for candidate in candidates
                ],
            )
            self.smart_clip_repository.update_project_progress(
                project_id,
                stage="building_candidates",
                total_asr_segments=len(asr_segments),
                kept_sales_segments=sum(1 for segment in resolved_segments if segment.get("keep_flag")),
                candidate_clip_count=len(stored_candidates),
            )
            self._generate_candidate_previews(
                project=project,
                candidates=[self._enrich_candidate(candidate) for candidate in stored_candidates],
                source_video_path=source_video["file_path"],
            )
            self.smart_clip_repository.update_project_status(
                project_id,
                status="ready",
                stage="ready",
                error_message=None,
            )
            logger.info(
                "智能切片项目分析完成: candidates=%s",
                len(stored_candidates),
                extra={"task_id": project_id, "stage": "smart_clip_project_ready"},
            )
            project = self.smart_clip_repository.get_project(project_id)
            return self._build_project_detail(project)
        except Exception as exc:
            logger.exception(
                "智能切片项目分析失败: %s",
                str(exc),
                extra={"task_id": project_id, "stage": "smart_clip_project_failed"},
            )
            self.smart_clip_repository.update_project_status(
                project_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
            )
            failed_project = self.smart_clip_repository.get_project(project_id)
            return self._build_project_detail(failed_project, allow_missing_source_video=True)

    def get_project_detail(self, project_id: str):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")
        return self._build_project_detail(project)

    def start_export(self, project_id: str):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")
        if str(project.get("status") or "") != "ready":
            raise ValueError("智能切片项目尚未完成分析")
        candidates = self.list_candidates(project_id)
        active_candidates = [candidate for candidate in candidates if candidate.get("status") == "active"]
        if not active_candidates:
            raise ValueError("没有可导出的候选切片")
        self.smart_clip_repository.update_project_progress(
            project_id,
            stage="exporting",
            export_total_count=len(active_candidates),
            export_completed_count=0,
            export_current_index=0,
        )
        self.smart_clip_repository.update_project_status(
            project_id,
            status="exporting",
            stage="exporting",
            error_message=None,
        )
        project = self.smart_clip_repository.get_project(project_id)
        return self._build_project_detail(project)

    def export_project(self, project_id: str, *, assume_started: bool = False):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")
        if str(project.get("status") or "") not in {"ready", "exporting"}:
            raise ValueError("智能切片项目尚未完成分析")
        if not assume_started:
            self.start_export(project_id)
            project = self.smart_clip_repository.get_project(project_id)

        source_video = self.video_repository.get(project["source_video_id"])
        if source_video is None:
            self.smart_clip_repository.update_project_progress(
                project_id,
                stage="failed",
                export_current_index=0,
                export_completed_count=0,
            )
            return self._build_failed_export_detail(project_id=project_id, error_message="源视频不存在")

        candidates = self.list_candidates(project_id)
        active_candidates = [candidate for candidate in candidates if candidate.get("status") == "active"]
        success_count = 0
        for current_index, candidate in enumerate(active_candidates, start=1):
            self.smart_clip_repository.update_project_progress(
                project_id,
                stage="exporting",
                export_total_count=len(active_candidates),
                export_current_index=current_index,
                export_completed_count=success_count,
            )
            self.smart_clip_repository.mark_candidate_exporting(candidate["id"])
            try:
                output_video_path = str(candidate.get("output_video_path") or "").strip()
                if not output_video_path or not Path(output_video_path).exists():
                    output_video_path = self._export_candidate_file(
                        project=project,
                        candidate=candidate,
                        source_video_path=source_video["file_path"],
                    )
                self.smart_clip_repository.mark_candidate_exported(
                    candidate["id"],
                    output_video_path=output_video_path,
                )
                success_count += 1
            except Exception as exc:
                logger.exception(
                    "智能切片候选导出失败: %s",
                    str(exc),
                    extra={"task_id": project_id, "candidate_id": candidate["id"], "stage": "smart_clip_export_failed"},
                )
                self.smart_clip_repository.mark_candidate_failed(candidate["id"], error_message=str(exc))
                self.smart_clip_repository.update_project_progress(
                    project_id,
                    stage="failed",
                    export_total_count=len(active_candidates),
                    export_current_index=current_index,
                    export_completed_count=success_count,
                )
                return self._build_failed_export_detail(project_id=project_id, error_message=str(exc))
            self.smart_clip_repository.update_project_progress(
                project_id,
                stage="exporting",
                export_total_count=len(active_candidates),
                export_current_index=current_index,
                export_completed_count=success_count,
            )

        self.smart_clip_repository.update_project_progress(
            project_id,
            stage="exported",
            export_total_count=len(active_candidates),
            export_current_index=len(active_candidates),
            export_completed_count=success_count,
        )
        self.smart_clip_repository.update_project_status(
            project_id,
            status="success",
            stage="exported",
            error_message=None,
        )
        project = self.smart_clip_repository.get_project(project_id)
        return self._build_project_detail(project)

    def list_candidates(self, project_id: str):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")
        return [self._enrich_candidate(candidate) for candidate in self.smart_clip_repository.list_candidates(project_id)]

    def delete_candidate(self, candidate_id: str):
        candidate = self.smart_clip_repository.get_candidate(candidate_id)
        if candidate is None:
            raise ValueError("候选切片不存在")
        if str(candidate.get("status") or "") != "active":
            raise ValueError("仅可删除未导出的候选切片")
        deleted = self.smart_clip_repository.soft_delete_candidate(candidate_id)
        return self._enrich_candidate(deleted)

    def get_candidate_stream_path(self, *, project_id: str, candidate_id: str):
        project = self.smart_clip_repository.get_project(project_id)
        if project is None:
            raise ValueError("智能切片项目不存在")
        candidate = self.smart_clip_repository.get_candidate(candidate_id)
        if candidate is None or candidate["project_id"] != project_id:
            raise ValueError("候选切片不存在")
        output_video_path = str(candidate.get("output_video_path") or "").strip()
        if not output_video_path:
            return None
        return Path(output_video_path)
