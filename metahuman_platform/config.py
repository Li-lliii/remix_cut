"""
数字人视频生成平台 - 配置文件
"""
import os
from pathlib import Path

# 基础路径
BASE_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = Path("/zhouzhibiao/gen_video")

# 临时文件目录
TEMP_DIR = BASE_DIR / "temp"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"

# 确保目录存在
TEMP_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ASR 配置 (FireRedASR)
ASR_MODEL_TYPE = "aed"
ASR_MODEL_PATH = PROJECT_ROOT / "bs_media_dem/FireRedASR/pretrained_models"

# TTS 配置 (IndexTTS)
TTS_CONFIG_PATH = PROJECT_ROOT / "bs_media_dem/index-tts/checkpoints/config.yaml"
TTS_MODEL_DIR = PROJECT_ROOT / "bs_media_dem/index-tts/checkpoints"
TTS_USE_FP16 = False

# 音频处理配置
AUDIO_SAMPLE_RATE = 16000
AUDIO_CLIP_DURATION = 5  # 语音克隆使用的音频时长(秒)

# ComfyUI 配置
COMFYUI_SERVER = "127.0.0.1:7040"
COMFYUI_INPUT_DIR = PROJECT_ROOT / "platform/ComfyUI/input"
COMFYUI_OUTPUT_DIR = PROJECT_ROOT / "platform/ComfyUI/output"

# 工作流配置
WORKFLOW_PATH = PROJECT_ROOT / "bs_media_dem/workstream/bs_media_metahuman_api.json"

# GPU 配置
GPU_DEVICE = "0"  # 使用的 GPU 编号
