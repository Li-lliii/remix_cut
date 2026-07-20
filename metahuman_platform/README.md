# MetaHuman Studio - 数字人视频生成平台

基于 AI 的口播数字人视频生成服务，使用 FastAPI + Vue.js 构建。

## 功能特点

- 🎙️ **声音克隆**: 上传参考音频，AI 自动克隆声音特征
- 🎬 **口型同步**: 使用 ComfyUI 工作流生成自然的口型动画
- 🚀 **简洁界面**: 现代化的白色极简设计风格
- ⚡ **异步处理**: 后台任务处理，实时进度反馈

## 系统架构

```
用户上传 (视频 + 音频 + 文本)
    ↓
[1] 音频裁剪 (取前5秒作为参考)
    ↓
[2] ASR 语音识别 (FireRedASR)
    ↓
[3] TTS 语音合成 (IndexTTS 声音克隆)
    ↓
[4] ComfyUI 工作流 (口型同步 + 视频生成)
    ↓
输出最终视频
```

## 项目结构

```
metahuman_platform/
├── server.py           # FastAPI 主服务器
├── config.py           # 配置文件
├── requirements.txt    # Python 依赖
├── services/
│   ├── __init__.py
│   ├── audio_service.py    # 音频处理服务 (ASR/TTS)
│   └── comfy_client.py     # ComfyUI 客户端
├── static/
│   └── index.html      # Vue.js 前端界面
├── temp/               # 临时文件目录
├── uploads/            # 上传文件目录
└── output/             # 输出文件目录
```

## 快速开始

### 1. 安装依赖

```bash
cd /zhouzhibiao/gen_video/bs_media_dem/metahuman_platform
pip install -r requirements.txt
```

### 2. 确保服务可用

- ComfyUI 服务运行在 `127.0.0.1:8088`
- FireRedASR 模型已下载到正确位置
- IndexTTS 检查点已下载到正确位置
- **重要**: IndexTTS 使用 `uv` 环境管理，确保在 index-tts 目录中可以执行 `uv run`

### 3. 启动服务

```bash
python server.py
```

或使用 uvicorn:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

### 4. 访问界面

打开浏览器访问: http://localhost:8000

## API 接口

### POST /api/generate

生成数字人视频

**参数:**
- `video`: 原始视频文件 (multipart/form-data)
- `audio`: 参考音频文件 (multipart/form-data)
- `text`: 要合成的文本内容 (form field)

**返回:**
```json
{
    "task_id": "uuid",
    "status": "pending",
    "status_url": "/api/status/{task_id}"
}
```

### GET /api/status/{task_id}

查询任务状态

**返回:**
```json
{
    "task_id": "uuid",
    "status": "processing",
    "progress": 45,
    "message": "正在生成视频...",
    "output_url": null
}
```

### GET /api/download/{filename}

下载生成的视频

### GET /api/health

健康检查

## 配置说明

编辑 `config.py` 修改以下配置:

```python
# ComfyUI 服务地址
COMFYUI_SERVER = "127.0.0.1:8088"

# GPU 设备
GPU_DEVICE = "0"

# 音频克隆时长 (秒)
AUDIO_CLIP_DURATION = 5
```

## 注意事项

1. **音频长度**: 参考音频建议 5-10 秒，过长反而影响克隆效果
2. **视频格式**: 支持 MP4、MOV 等常见格式
3. **GPU 内存**: 需要足够的显存来运行 ASR、TTS 和视频生成模型
4. **处理时间**: 完整流程可能需要 5-15 分钟，请耐心等待

## 技术栈

- **后端**: FastAPI + Python 3.10+
- **前端**: Vue.js 3 + 原生 CSS
- **ASR**: FireRedASR
- **TTS**: IndexTTS
- **视频生成**: ComfyUI + Wan2.1

## License

Internal Use Only




unset BS_MEDIA_DATABASE_URL

export BS_MEDIA_PLATFORM_LOG_FILE=/tmp/bs-media-platform.log
export BS_MEDIA_MINIO_ENDPOINT=127.0.0.1:9000
export BS_MEDIA_MINIO_ACCESS_KEY=minioadmin
export BS_MEDIA_MINIO_SECRET_KEY=minioadmin
export BS_MEDIA_MINIO_BUCKET=bs-media
export BS_MEDIA_MINIO_SECURE=false

../.venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload