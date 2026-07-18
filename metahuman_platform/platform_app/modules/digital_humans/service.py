from __future__ import annotations

import re
from pathlib import Path
import shutil
from typing import Iterable

from platform_app.modules.digital_humans.repository import (
    DigitalHumanAssetRepository,
    DigitalHumanGenerationTaskRepository,
    DigitalHumanProfileRepository,
    DigitalHumanRepository,
)
from platform_app.modules.digital_humans.comfy_adapter import DigitalHumanComfyAdapter
from platform_app.modules.digital_humans.progress import DigitalHumanProgress
from platform_app.modules.digital_humans.storage import DigitalHumanStorage, UploadObjectSpec
from platform_app.modules.materials.constants import (
    ASSET_TYPE_AUDIO,
    ASSET_TYPE_IMAGE,
    ASSET_TYPE_VIDEO,
    DIGITAL_HUMAN_CREATION_PARTITION,
)
from platform_app.modules.materials.service import MaterialService


class DigitalHumanService:
    TRAINING_STATUSES = {"training_pending", "pending", "queued", "submitted", "running", "training"}
    ACTIVE_STATUSES = {"active", "success", "completed"}
    FAILED_STATUSES = {"failed", "cancelled"}

    def __init__(self, *, db_path: Path, uploads_dir: Path):
        self.db_path = Path(db_path)
        self.uploads_dir = Path(uploads_dir)
        self.digital_human_repository = DigitalHumanRepository(self.db_path)
        self.profile_repository = DigitalHumanProfileRepository(self.db_path)
        self.asset_repository = DigitalHumanAssetRepository(self.db_path)
        self.task_repository = DigitalHumanGenerationTaskRepository(self.db_path)
        self.storage = DigitalHumanStorage()
        self.progress = DigitalHumanProgress()
        self.comfy_adapter = DigitalHumanComfyAdapter()

    def _asset_preview_url(self, asset: dict) -> str:
        if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
            try:
                return self.storage.result_download_url(asset["storage_key"])
            except Exception:
                return ""
        return f"/api/digital-humans/assets/{asset['id']}/stream"

    def _enrich_asset_for_display(self, asset: dict | None):
        if asset is None:
            return None
        enriched = dict(asset)
        enriched["preview_url"] = self._asset_preview_url(asset)
        return enriched

    def _parse_tags(self, raw_tags: str | Iterable[str] | None) -> list[str]:
        if raw_tags is None:
            return []
        if isinstance(raw_tags, str):
            parts = re.split(r"[,，;；\s]+", raw_tags)
        else:
            parts = [str(item) for item in raw_tags]
        tags = []
        seen = set()
        for part in parts:
            tag = part.strip()
            if tag and tag not in seen:
                tags.append(tag)
                seen.add(tag)
        return tags

    def _save_asset(
        self,
        *,
        digital_human_id: str,
        asset_type: str,
        filename: str,
        content: bytes,
        content_type: str,
    ):
        if not content:
            raise ValueError(f"{asset_type} 文件为空")
        storage_key = self.storage.upload_asset_bytes(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            filename=filename,
            content=content,
            content_type=content_type,
        )
        return self.asset_repository.create(
            digital_human_id=digital_human_id,
            asset_type=asset_type,
            filename=filename,
            file_path=f"minio://{self.storage.settings.minio_bucket}/{storage_key}",
            content_type=content_type,
            storage_backend="minio",
            storage_key=storage_key,
            metadata={"source": "create_from_materials"},
        )

    def _save_asset_from_material(
        self,
        *,
        digital_human_id: str,
        digital_human_asset_type: str,
        material_asset_id: str,
        expected_material_type: str,
    ):
        material_service = MaterialService(db_path=self.db_path, uploads_dir=self.uploads_dir)
        material = material_service.get_asset(material_asset_id)
        if material.get("partition_name") != DIGITAL_HUMAN_CREATION_PARTITION:
            raise ValueError("请选择创建数字人素材库中的素材")
        if material.get("asset_type") != expected_material_type:
            raise ValueError(f"素材类型不匹配，需要 {expected_material_type}")
        return self.asset_repository.create(
            digital_human_id=digital_human_id,
            asset_type=digital_human_asset_type,
            filename=material.get("filename") or f"{digital_human_asset_type}",
            file_path=material.get("file_path") or "",
            content_type=material.get("content_type") or "application/octet-stream",
            storage_backend=material.get("storage_backend") or "minio",
            storage_key=material.get("storage_key") or "",
            metadata={
                "source": "material_library",
                "source_material_asset_id": material["id"],
                "source_material_partition": material.get("partition_name"),
                "source_material_type": material.get("asset_type"),
            },
        )

    def _build_training_prompt(
        self,
        *,
        name: str,
        avatar_type: str,
        gender: str,
        department: str,
        organization: str,
        speaker_name: str,
        tags: list[str],
        description: str,
    ) -> str:
        values = [
            f"数字人名称：{name}",
            f"形象类型：{avatar_type}",
            f"性别：{gender}" if gender else "",
            f"所属科室/部门：{department}",
            f"归属机构：{organization}" if organization else "",
            f"主讲人：{speaker_name}" if speaker_name else "",
            f"标签：{'、'.join(tags)}" if tags else "",
            f"简介：{description}" if description else "",
        ]
        return "\n".join(value for value in values if value)

    def create_avatar_training_task(
        self,
        *,
        name: str,
        avatar_type: str,
        gender: str,
        department: str,
        organization: str,
        speaker_name: str,
        tags: str,
        style: str,
        description: str,
        talking_video: tuple[str, bytes, str] | None = None,
        person_image: tuple[str, bytes, str] | None = None,
        voice_sample: tuple[str, bytes, str] | None = None,
        talking_video_material_id: str = "",
        person_image_material_id: str = "",
        voice_sample_material_id: str = "",
    ):
        name = name.strip()
        avatar_type = avatar_type.strip()
        department = department.strip()
        if not name:
            raise ValueError("数字人名称必填")
        if not avatar_type:
            raise ValueError("形象类型必填")
        if not department:
            raise ValueError("所属科室/部门必填")
        if talking_video is None and not talking_video_material_id:
            raise ValueError("口播视频必填")
        if talking_video is not None and not talking_video[1]:
            raise ValueError("talking_video 文件为空")

        digital_human = self.digital_human_repository.create(
            name=name,
            avatar_type=avatar_type,
            gender=gender.strip(),
            status="training_pending",
        )
        parsed_tags = self._parse_tags(tags)
        profile = self.profile_repository.create(
            digital_human_id=digital_human["id"],
            department=department,
            organization=organization.strip(),
            speaker_name=speaker_name.strip(),
            tags=parsed_tags,
            style=style.strip(),
            description=description.strip(),
            metadata={"source_type": "material_avatar_training"},
        )

        if talking_video_material_id:
            talking_video_asset = self._save_asset_from_material(
                digital_human_id=digital_human["id"],
                digital_human_asset_type="talking_video",
                material_asset_id=talking_video_material_id,
                expected_material_type=ASSET_TYPE_VIDEO,
            )
        else:
            assert talking_video is not None
            talking_video_asset = self._save_asset(
                digital_human_id=digital_human["id"],
                asset_type="talking_video",
                filename=talking_video[0],
                content=talking_video[1],
                content_type=talking_video[2],
            )
        assets = [talking_video_asset]
        primary_asset = None
        if person_image_material_id:
            primary_asset = self._save_asset_from_material(
                digital_human_id=digital_human["id"],
                digital_human_asset_type="person_image",
                material_asset_id=person_image_material_id,
                expected_material_type=ASSET_TYPE_IMAGE,
            )
            assets.append(primary_asset)
        elif person_image is not None:
            primary_asset = self._save_asset(
                digital_human_id=digital_human["id"],
                asset_type="person_image",
                filename=person_image[0],
                content=person_image[1],
                content_type=person_image[2],
            )
            assets.append(primary_asset)
        if voice_sample_material_id:
            assets.append(
                self._save_asset_from_material(
                    digital_human_id=digital_human["id"],
                    digital_human_asset_type="voice_sample",
                    material_asset_id=voice_sample_material_id,
                    expected_material_type=ASSET_TYPE_AUDIO,
                )
            )
        elif voice_sample is not None:
            assets.append(
                self._save_asset(
                    digital_human_id=digital_human["id"],
                    asset_type="voice_sample",
                    filename=voice_sample[0],
                    content=voice_sample[1],
                    content_type=voice_sample[2],
                )
            )
        if primary_asset is not None:
            digital_human = self.digital_human_repository.update_primary_asset(
                digital_human["id"],
                primary_asset["id"],
                status="training_pending",
            )
        task = self.task_repository.create(
            digital_human_id=digital_human["id"],
            task_type="material_avatar_build",
            status="pending",
            prompt_text=self._build_training_prompt(
                name=name,
                avatar_type=avatar_type,
                gender=gender,
                department=department,
                organization=organization,
                speaker_name=speaker_name,
                tags=parsed_tags,
                description=description,
            ),
            workflow_name="material_avatar_training",
        )

        return {
            "digital_human": digital_human,
            "profile": profile,
            "assets": assets,
            "primary_asset": primary_asset,
            "generation_task": task,
        }

    def list_digital_humans(self):
        return [
            self._with_profile_and_primary_asset(digital_human)
            for digital_human in self.digital_human_repository.list()
        ]

    def list_digital_human_library(
        self,
        *,
        search: str | None = None,
        avatar_type: str | None = None,
        status: str | None = None,
    ):
        records = [self._build_library_item(item) for item in self.digital_human_repository.list()]
        filtered = [
            record
            for record in records
            if self._matches_library_filters(
                record,
                search=search,
                avatar_type=avatar_type,
                status=status,
            )
        ]
        return {
            "items": filtered,
            "total_count": len(records),
            "filtered_count": len(filtered),
            "summary": self._build_library_summary(records),
            "filters": self._build_library_filter_options(records),
        }

    def get_digital_human_detail(self, digital_human_id: str):
        digital_human = self.digital_human_repository.get(digital_human_id)
        if digital_human is None:
            raise ValueError("数字人不存在")
        detail = self._with_profile_and_primary_asset(digital_human)
        detail["assets"] = [
            self._enrich_asset_for_display(asset)
            for asset in self.asset_repository.list_by_digital_human(digital_human_id)
        ]
        detail["generation_tasks"] = self.task_repository.list_by_digital_human(digital_human_id)
        return detail

    def get_task(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("数字人训练任务不存在")
        return task

    def create_object_upload_task(
        self,
        *,
        digital_human_id: str,
        task_type: str,
        workflow_name: str,
        prompt_text: str,
        files: list[UploadObjectSpec],
        params: dict | None = None,
    ):
        if self.digital_human_repository.get(digital_human_id) is None:
            raise ValueError("数字人不存在")
        task_params = dict(params or {})
        task_params["upload_files"] = [
            {
                "field": file_spec.field,
                "filename": file_spec.filename,
                "content_type": file_spec.content_type,
            }
            for file_spec in files
        ]
        task = self.task_repository.create(
            digital_human_id=digital_human_id,
            task_type=task_type,
            status="uploading",
            prompt_text=prompt_text,
            workflow_name=workflow_name,
            input_asset_keys={},
            params=task_params,
        )
        input_keys, uploads = self.storage.create_presigned_uploads(
            digital_human_id=digital_human_id,
            task_id=task["id"],
            files=files,
        )
        # 创建任务后才有 task_id，因此 object key 在这里回填到同一条任务记录。
        task = self.task_repository.set_input_asset_keys(task["id"], input_asset_keys=input_keys)
        return {"task": task, "uploads": uploads}

    def submit_object_upload_task(self, task_id: str):
        task = self.task_repository.get(task_id)
        if task is None:
            raise ValueError("数字人生成任务不存在")
        input_keys = task.get("input_asset_keys_json") or {}
        self.storage.assert_objects_uploaded(input_keys)
        self._register_uploaded_input_assets(task)
        task = self.task_repository.update_status(task_id, status="queued")
        try:
            from platform_app.modules.digital_humans.tasks import run_generation_task

            run_generation_task.delay(task_id)
        except RuntimeError as exc:
            task = self.task_repository.update_status(task_id, status="queued", error_message=str(exc))
        return task

    def get_task_with_progress(self, task_id: str):
        task = self.get_task(task_id)
        progress = {}
        try:
            progress = self.progress.get(task_id)
        except Exception:
            progress = {"progress": 0, "stage": task.get("status", "unknown"), "message": "", "extra": {}}
        result_download_url = ""
        if task.get("result_key"):
            try:
                result_download_url = self.storage.result_download_url(task["result_key"])
            except Exception:
                result_download_url = ""
        return {"task": task, "progress": progress, "result_download_url": result_download_url}

    def submit_avatar_training_to_comfyui(self, task_id: str):
        task = self.get_task(task_id)
        if task["task_type"] != "material_avatar_build":
            raise ValueError("只有 material_avatar_build 任务可以提交数字人训练")
        if task["status"] not in {"pending", "training_pending", "failed"}:
            raise ValueError(f"当前任务状态不允许提交 ComfyUI: {task['status']}")
        assets = self.asset_repository.list_by_digital_human(task["digital_human_id"])
        local_assets = self._materialize_assets_for_comfyui(task=task, assets=assets)
        result = self.comfy_adapter.submit_avatar_training(task=task, assets=local_assets)
        updated = self.task_repository.set_backend_job(
            task_id,
            backend_job_id=result["backend_job_id"],
            status="submitted",
        )
        return {"task": updated, "comfyui": result}

    def _materialize_assets_for_comfyui(self, *, task: dict, assets: list[dict]) -> list[dict]:
        target_dir = self.uploads_dir / "digital_humans" / task["digital_human_id"] / "comfyui" / task["id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        materialized = []
        for asset in assets:
            copied = dict(asset)
            if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
                suffix = Path(asset["filename"]).suffix
                target_path = target_dir / f"{asset['asset_type']}{suffix}"
                self.storage.download_asset(storage_key=asset["storage_key"], target_path=target_path)
                copied["file_path"] = str(target_path)
            elif asset.get("file_path"):
                source = Path(asset["file_path"])
                if source.exists():
                    target_path = target_dir / source.name
                    if source.resolve() != target_path.resolve():
                        shutil.copyfile(source, target_path)
                    copied["file_path"] = str(target_path)
            materialized.append(copied)
        return materialized

    def _register_uploaded_input_assets(self, task: dict):
        input_keys = task.get("input_asset_keys_json") or {}
        params = task.get("params_json") or {}
        upload_files = {
            item.get("field"): item
            for item in params.get("upload_files", [])
            if isinstance(item, dict) and item.get("field")
        }
        assets = []
        for field, storage_key in input_keys.items():
            existing = self.asset_repository.get_by_storage_key(storage_key)
            if existing is not None:
                assets.append(existing)
                continue
            upload_file = upload_files.get(field, {})
            filename = upload_file.get("filename") or Path(storage_key).name
            content_type = upload_file.get("content_type") or "application/octet-stream"
            assets.append(
                self.asset_repository.create(
                    digital_human_id=task["digital_human_id"],
                    asset_type=field,
                    filename=filename,
                    file_path=f"minio://{self.storage.settings.minio_bucket}/{storage_key}",
                    content_type=content_type,
                    storage_backend="minio",
                    storage_key=storage_key,
                    metadata={
                        "source": "object_upload_task",
                        "task_id": task["id"],
                        "task_type": task["task_type"],
                    },
                )
            )
        return assets

    def _with_profile_and_primary_asset(self, digital_human: dict):
        primary_asset = None
        if digital_human.get("primary_asset_id"):
            primary_asset = self.asset_repository.get(digital_human["primary_asset_id"])
        return {
            "digital_human": digital_human,
            "profile": self.profile_repository.get_by_digital_human(digital_human["id"]),
            "primary_asset": self._enrich_asset_for_display(primary_asset),
        }

    def _build_library_item(self, digital_human: dict):
        profile = self.profile_repository.get_by_digital_human(digital_human["id"]) or {}
        assets = self.asset_repository.list_by_digital_human(digital_human["id"])
        tasks = self.task_repository.list_by_digital_human(digital_human["id"])
        display_asset = self._pick_display_asset(digital_human, assets)
        status_group = self._status_group(digital_human.get("status", ""))
        return {
            "id": digital_human["id"],
            "name": digital_human.get("name", ""),
            "avatar_type": digital_human.get("avatar_type", ""),
            "gender": digital_human.get("gender", ""),
            "status": digital_human.get("status", ""),
            "status_group": status_group,
            "status_label": self._status_label(status_group, digital_human.get("status", "")),
            "department": profile.get("department", ""),
            "organization": profile.get("organization", ""),
            "speaker_name": profile.get("speaker_name", ""),
            "tags": profile.get("tags_json") or [],
            "style": profile.get("style", ""),
            "description": profile.get("description", ""),
            "profile": profile,
            "display_asset": self._enrich_asset_for_display(display_asset),
            "primary_asset": self._enrich_asset_for_display(
                self.asset_repository.get(digital_human["primary_asset_id"])
                if digital_human.get("primary_asset_id")
                else None
            ),
            "assets_count": len(assets),
            "latest_task": tasks[0] if tasks else None,
            "created_at": digital_human.get("created_at"),
            "updated_at": digital_human.get("updated_at"),
        }

    def _pick_display_asset(self, digital_human: dict, assets: list[dict]):
        if digital_human.get("primary_asset_id"):
            for asset in assets:
                if asset["id"] == digital_human["primary_asset_id"]:
                    return asset
        priority = {"person_image": 0, "avatar_image": 1, "cover_image": 2, "talking_video": 3}
        return min(assets, key=lambda asset: priority.get(asset.get("asset_type"), 100), default=None)

    def _matches_library_filters(
        self,
        record: dict,
        *,
        search: str | None,
        avatar_type: str | None,
        status: str | None,
    ) -> bool:
        normalized_type = self._normalize_filter_value(avatar_type)
        if normalized_type and record.get("avatar_type") != normalized_type:
            return False

        normalized_status = self._normalize_filter_value(status)
        if normalized_status and normalized_status not in {record.get("status"), record.get("status_group")}:
            return False

        keyword = self._normalize_filter_value(search)
        if not keyword:
            return True
        searchable = [
            record.get("name", ""),
            record.get("avatar_type", ""),
            record.get("gender", ""),
            record.get("department", ""),
            record.get("organization", ""),
            record.get("speaker_name", ""),
            record.get("style", ""),
            record.get("description", ""),
            " ".join(record.get("tags") or []),
        ]
        return keyword.lower() in " ".join(str(value) for value in searchable).lower()

    def _build_library_summary(self, records: list[dict]):
        status_counts = {}
        type_counts = {}
        for record in records:
            status = record.get("status") or "unknown"
            status_group = record.get("status_group") or "unknown"
            avatar_type = record.get("avatar_type") or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            if status_group != status:
                status_counts[status_group] = status_counts.get(status_group, 0) + 1
            type_counts[avatar_type] = type_counts.get(avatar_type, 0) + 1
        return {
            "total_count": len(records),
            "active_count": status_counts.get("active", 0),
            "training_count": status_counts.get("training", 0),
            "failed_count": status_counts.get("failed", 0),
            "status_counts": status_counts,
            "type_counts": type_counts,
        }

    def _build_library_filter_options(self, records: list[dict]):
        types = sorted({record.get("avatar_type") for record in records if record.get("avatar_type")})
        statuses = {}
        for record in records:
            if record.get("status"):
                statuses[record["status"]] = self._status_label(record.get("status_group", ""), record["status"])
            if record.get("status_group"):
                statuses[record["status_group"]] = self._status_label(record["status_group"], record["status_group"])
        return {
            "avatar_types": types,
            "statuses": [
                {"value": value, "label": label}
                for value, label in sorted(statuses.items(), key=lambda item: item[0])
            ],
        }

    def _status_group(self, status: str) -> str:
        if status in self.ACTIVE_STATUSES:
            return "active"
        if status in self.TRAINING_STATUSES:
            return "training"
        if status in self.FAILED_STATUSES:
            return "failed"
        if status in {"draft"}:
            return "draft"
        return status or "unknown"

    def _status_label(self, status_group: str, status: str) -> str:
        labels = {
            "active": "已激活",
            "training": "训练中",
            "failed": "失败",
            "draft": "草稿",
            "unknown": "未知",
        }
        return labels.get(status_group) or labels.get(status) or status

    def _normalize_filter_value(self, value: str | None) -> str:
        if value is None:
            return ""
        normalized = value.strip()
        if normalized in {"", "all", "全部", "全部类型", "全部状态"}:
            return ""
        return normalized
