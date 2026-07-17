import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from platform_app.modules.materials.service import MaterialService
from platform_app.repositories.asr_repository import AsrRepository
from platform_app.repositories.role_repository import RoleRepository
from platform_app.services.background_runner import run_in_background
from platform_app.repositories.video_repository import VideoRepository
from platform_app.services.asr_adapter import AsrAdapter
from platform_app.services.video_service import VideoService
from platform_app.settings import get_settings

#接收请求、校验资源是否存在、调用仓储/服务、返回 JSON 或视频文件流。
router = APIRouter(tags=["videos"])

#这是接口请求体模型，用于“置顶/取消置顶视频”。
class PinPayload(BaseModel):
    is_pinned: bool

#查询某个角色的视频列表
@router.get("/api/roles/{role_id}/videos")#接口路径
async def list_role_videos(role_id: str):
    settings = get_settings()#读取配置，拿到数据库路径
    videos = VideoRepository(settings.database_path).list_by_role(role_id)#通过 VideoRepository 查询该角色的视频列表,视频数据表的操作工具类，把底层 SQL 封装起来，供 API 层和 Service 层调用。
    return {"items": videos}

#上传角色视频,给某个角色上传视频
@router.post("/api/roles/{role_id}/videos/upload")
async def upload_role_video(role_id: str, video: UploadFile = File(...)):
    settings = get_settings()
    role_repository = RoleRepository(settings.database_path)#检查角色是否存在
    if role_repository.get(role_id) is None:
        raise HTTPException(status_code=404, detail="角色不存在")

    try:
        #读取上传文件内容
        content = await video.read()
        if not content:
            raise HTTPException(status_code=400, detail="视频文件为空")
       #创建 VideoService,把数据库路径、上传目录、ASR 适配器传进去
        service = VideoService(
            db_path=settings.database_path,
            uploads_dir=settings.uploads_dir,
            asr_adapter=AsrAdapter(
                settings.asr_mode,
                service_base_url=settings.asr_service_base_url,
                connect_timeout_sec=settings.algo_connect_timeout_sec,
                read_timeout_sec=settings.algo_read_timeout_sec,
            ),
        )
        #保存视频文件并写数据库,会保存文件、获取视频时长/比例，并创建视频记录。
        created = service.save_upload(role_id=role_id, filename=video.filename or "upload.mp4", content=content)
        #后台启动 ASR,上传接口不会等 ASR 全部完成，而是直接返回视频记录；ASR 在后台慢慢跑。
        run_in_background(service.process_video_asr, created["id"])
        return created
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传视频失败: {exc}") from exc


@router.patch("/api/videos/{video_id}/pin")
async def update_video_pin(video_id: str, payload: PinPayload):
    settings = get_settings()
    repository = VideoRepository(settings.database_path)
    video = repository.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    return repository.set_pinned(video_id, payload.is_pinned)

#删除视频
@router.delete("/api/videos/{video_id}")
async def delete_video(video_id: str):
    settings = get_settings()
    repository = VideoRepository(settings.database_path)
    video = repository.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    repository.soft_delete(video_id)
    return {"success": True}

#查询视频 ASR 结果
@router.get("/api/videos/{video_id}/asr")
async def get_video_asr(video_id: str):
    settings = get_settings()
    video_repository = VideoRepository(settings.database_path)
    asr_repository = AsrRepository(settings.database_path)
    video = video_repository.get(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    result = asr_repository.get_by_video(video_id)
    if result is None:
        summary_source = "pending"
        return {
            "video_id": video_id,
            "status": video["asr_status"],
            "summary_status": summary_source,
            "summary_source": summary_source,
            "summary": "",
            "full_text": None,
            "segments": [],
            "error_message": video.get("asr_error_message"),
            "summary_error_message": None,
        }
    summary_status = result.get("summary_status") or "pending"
    summary_text = result.get("summary_text") or ""
    summary_error_message = result.get("summary_error_message")
    if summary_status != "success":
        summary_text = ""
    return {
        "video_id": video_id,
        "status": video["asr_status"],
        "summary_status": summary_status,
        "summary_source": summary_status,
        "summary": summary_text,
        "full_text": result["full_text"],
        "segments": result["segments"],
        "error_message": video.get("asr_error_message"),
        "summary_error_message": summary_error_message,
    }

#视频流播放
@router.get("/api/videos/{video_id}/stream")
async def stream_video(video_id: str):
    settings = get_settings()
    repository = VideoRepository(settings.database_path)
    video = repository.get(video_id)#查视频记录
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    if video.get("material_asset_id"):
        material_service = MaterialService(db_path=settings.database_path, uploads_dir=settings.uploads_dir)
        try:
            asset = material_service.get_asset(video["material_asset_id"])
            if asset.get("storage_backend") == "minio" and asset.get("storage_key"):
                return RedirectResponse(material_service.result_download_url(asset))
        except Exception:
            pass
    #检查数据库里记录的文件是否存在
    file_path = Path(video["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)
