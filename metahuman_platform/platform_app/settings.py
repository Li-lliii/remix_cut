import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppSettings:
    base_dir: Path
    data_dir: Path
    uploads_dir: Path
    work_dir: Path
    temp_dir: Path
    generated_dir: Path
    static_dir: Path
    database_path: Path
    default_asr_mode: str
    asr_mode: str
    tts_mode: str
    comfy_mode: str
    asr_service_base_url: str
    tts_service_base_url: str
    comfy_service_base_url: str
    algo_connect_timeout_sec: float
    algo_read_timeout_sec: float
    database_url: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    minio_presign_expiry_sec: int
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str


def get_settings() -> AppSettings:
    data_dir = Path(os.environ.get("BS_MEDIA_DATA_DIR", str(BASE_DIR / "data"))).resolve()
    uploads_dir = Path(
        os.environ.get("BS_MEDIA_UPLOADS_DIR", str(BASE_DIR / "uploads"))
    ).resolve()
    work_dir = Path(os.environ.get("BS_MEDIA_WORK_DIR", str(BASE_DIR / "work"))).resolve()
    temp_dir = Path(os.environ.get("BS_MEDIA_TEMP_DIR", str(work_dir / "temp"))).resolve()
    generated_dir = Path(
        os.environ.get("BS_MEDIA_GENERATED_DIR", str(work_dir / "generated"))
    ).resolve()
    static_dir = BASE_DIR / "static"
    database_path = data_dir / "app.db"

    data_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    generated_dir.mkdir(parents=True, exist_ok=True)
    asr_service_host = os.environ.get("BS_MEDIA_ASR_SERVICE_HOST", "127.0.0.1")
    tts_service_host = os.environ.get("BS_MEDIA_TTS_SERVICE_HOST", "127.0.0.1")
    comfy_service_host = os.environ.get("BS_MEDIA_COMFY_SERVICE_HOST", "127.0.0.1")
    asr_service_port = int(os.environ.get("BS_MEDIA_ASR_SERVICE_PORT", "7000"))
    tts_service_port = int(os.environ.get("BS_MEDIA_TTS_SERVICE_PORT", "7001"))
    comfy_service_port = int(os.environ.get("BS_MEDIA_COMFY_SERVICE_PORT", "7002"))
    connect_timeout_sec = float(os.environ.get("BS_MEDIA_ALGO_CONNECT_TIMEOUT_SEC", "10"))
    read_timeout_sec = float(
        os.environ.get(
            "BS_MEDIA_ALGO_READ_TIMEOUT_SEC",
            os.environ.get("BS_MEDIA_ALGO_HTTP_TIMEOUT_SEC", "600"),
        )
    )
    asr_mode = os.environ.get("BS_MEDIA_ASR_MODE", os.environ.get("BS_MEDIA_DEFAULT_ASR_MODE", "service"))
    tts_mode = os.environ.get("BS_MEDIA_TTS_MODE", "service")
    comfy_mode = os.environ.get("BS_MEDIA_COMFY_MODE", "legacy")
    redis_url = os.environ.get("BS_MEDIA_REDIS_URL", "redis://127.0.0.1:6379/0")
    celery_broker_url = os.environ.get("BS_MEDIA_CELERY_BROKER_URL", "amqp://guest:guest@127.0.0.1:5672//")

    return AppSettings(
        base_dir=BASE_DIR,
        data_dir=data_dir,
        uploads_dir=uploads_dir,
        work_dir=work_dir,
        temp_dir=temp_dir,
        generated_dir=generated_dir,
        static_dir=static_dir,
        database_path=database_path,
        default_asr_mode=asr_mode,
        asr_mode=asr_mode,
        tts_mode=tts_mode,
        comfy_mode=comfy_mode,
        asr_service_base_url=f"http://{asr_service_host}:{asr_service_port}",
        tts_service_base_url=f"http://{tts_service_host}:{tts_service_port}",
        comfy_service_base_url=f"http://{comfy_service_host}:{comfy_service_port}",
        algo_connect_timeout_sec=connect_timeout_sec,
        algo_read_timeout_sec=read_timeout_sec,
        database_url=os.environ.get("BS_MEDIA_DATABASE_URL", f"sqlite:///{database_path}"),
        minio_endpoint=os.environ.get("BS_MEDIA_MINIO_ENDPOINT", "127.0.0.1:9000"),
        minio_access_key=os.environ.get("BS_MEDIA_MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.environ.get("BS_MEDIA_MINIO_SECRET_KEY", "minioadmin"),
        minio_bucket=os.environ.get("BS_MEDIA_MINIO_BUCKET", "bs-media"),
        minio_secure=os.environ.get("BS_MEDIA_MINIO_SECURE", "false").lower() in {"1", "true", "yes"},
        minio_presign_expiry_sec=int(os.environ.get("BS_MEDIA_MINIO_PRESIGN_EXPIRY_SEC", "3600")),
        redis_url=redis_url,
        celery_broker_url=celery_broker_url,
        celery_result_backend=os.environ.get("BS_MEDIA_CELERY_RESULT_BACKEND", redis_url),
    )
