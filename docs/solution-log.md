# 问题解决方案记录

以后说“记录解决方案”时，统一追加到这个文件。

## 2026-07-20 AI 变身换口播 TTS 调通记录

### 背景

目标流程：

```text
source_video_id + speech_text
-> replace_speech
-> TTS 生成 wav
-> comfyui-gateway 调 replace_speech_api.json
-> ComfyUI 对口型
-> 结果上传 MinIO
```

本次已经解决的是 TTS 阶段：

```text
speech_text -> Qwen3-TTS -> wav 输出成功
```

### 关键结论

- `7001` 是 TTS 服务端口。
- `7000` 是 ASR 服务端口。
- 换口播会先请求 TTS，把 `speech_text` 变成 wav，再进入 ComfyUI。
- TTS 优先用原视频截取参考音频做音色克隆；失败后使用默认音色。
- Docker 内部路径是 `/app/metahuman_platform/...`，宿主机 TTS 路径是 `/home/kemove/.../metahuman_platform/...`，混合部署时必须做路径映射。

### 遇到的问题与处理

#### 1. TTS 服务未启动

现象：

```text
TTS 服务请求失败: [Errno 111] Connection refused
```

原因：

`replace_speech` 请求 `http://host.docker.internal:7001`，但宿主机 `7001` 没有 TTS 服务。

处理：

```bash
curl http://localhost:7001/health
```

如果不通，启动 TTS。

#### 2. Qwen3-TTS 路径不一致

现象：

```text
ImportError: cannot import name 'Qwen3TTSModel' from 'qwen_tts'
```

原因：

服务器上有两份 `Qwen3-TTS`，服务默认解析到的那份缺少正确导出。

处理：

启动 TTS 时显式指定可用的 Qwen3-TTS 路径：

```bash
BS_MEDIA_QWEN3_TTS_ROOT=/home/kemove/zhouzhibiao/bs_media/function/remix_cut/Qwen3-TTS \
BS_MEDIA_QWEN3_TTS_MODEL=/home/kemove/zhouzhibiao/bs_media/function/remix_cut/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-Base \
python -m uvicorn metahuman_platform.algorithm_services.tts_service:app --host 0.0.0.0 --port 7001
```

代码也已支持：

```text
BS_MEDIA_QWEN3_TTS_ROOT
BS_MEDIA_QWEN3_TTS_MODEL
```

#### 3. TTS 启动依赖 ASR

现象：

```text
RuntimeError: ASR 服务未就绪
```

原因：

TTS 克隆原视频声音时，需要 ASR 识别参考音频文本。

处理：

先启动 ASR：

```bash
python -m uvicorn metahuman_platform.algorithm_services.asr_service:app --host 0.0.0.0 --port 7000
```

确认：

```bash
curl http://localhost:7000/ready
```

然后再启动 TTS。

#### 4. Python sox 缺失

现象：

```text
ModuleNotFoundError: No module named 'sox'
```

处理：

在 TTS 使用的 Python 环境里安装：

```bash
pip install sox
```

如果系统命令也缺失：

```bash
sudo apt-get install -y sox
```

#### 5. Docker 路径和宿主机路径不一致

现象：

```text
视频文件不存在: /app/metahuman_platform/work/temp/...
默认参考音色不存在: /app/metahuman_platform/assets/default_voice/dongbei_clone_5s.wav
```

原因：

`celery-worker` 在 Docker 内传的是 `/app/metahuman_platform/...`，但 TTS 服务跑在宿主机，看不到 `/app/...`。

处理：

TTS 服务增加路径映射：

```text
/app/metahuman_platform -> 宿主机项目/metahuman_platform
```

启动 TTS 时显式传：

```bash
BS_MEDIA_PATH_MAPPINGS=/app/metahuman_platform=/home/kemove/liwenmin/AI-Human/bs_media/.worktrees/main-release/function/remix_cut/metahuman_platform
```

同时 `docker-compose.yml` 将 work 目录改成 bind mount：

```yaml
./metahuman_platform/work:/app/metahuman_platform/work
```

#### 6. SQLite readonly database

现象：

```text
attempt to write a readonly database
```

原因：

容器改成非 root 用户运行后，Docker named volume 里的 `/app/metahuman_platform/data/app.db` 仍归 root。

处理：

```bash
docker compose exec -u root web-api chown -R 1000:1000 /app/metahuman_platform/data /app/metahuman_platform/uploads
docker compose exec -u root web-api chmod -R u+rwX /app/metahuman_platform/data /app/metahuman_platform/uploads
docker compose restart web-api celery-worker
```

确认：

```bash
docker compose exec web-api ls -la /app/metahuman_platform/data
```

#### 7. 容器非 root 后日志写 `/logs` 失败

现象：

```text
PermissionError: [Errno 13] Permission denied: '/logs'
```

处理：

`docker-compose.yml` 给 `web-api` 设置：

```yaml
BS_MEDIA_PLATFORM_LOG_FILE: /app/metahuman_platform/work/logs/platform/uvicorn-7028.log
```

#### 8. 新 task 的 TTS 输出目录权限反复失败

现象：

```text
Permission denied: .../replace_speech/tts/<task_id>.wav.tmp
```

原因：

每个新任务目录由容器创建，如果容器用 root 写 bind mount，宿主机 TTS 用户无法写 wav。

处理：

`docker-compose.yml` 中 `web-api`、`celery-worker`、`comfyui-gateway` 使用宿主机 UID/GID：

```yaml
user: "${BS_MEDIA_UID:-1000}:${BS_MEDIA_GID:-1000}"
```

`.env` 中写：

```bash
BS_MEDIA_UID=1000
BS_MEDIA_GID=1000
```

已有目录修权限：

```bash
sudo chown -R kemove:kemove metahuman_platform/work metahuman_platform/data metahuman_platform/uploads
chmod -R u+rwX metahuman_platform/work metahuman_platform/data metahuman_platform/uploads
```

#### 9. soundfile 写 wav 报 System error

现象：

```text
soundfile.LibsndfileError: Error opening '...wav': System error
```

排查结果：

- `touch` 目标目录成功。
- 手动 `soundfile.write()` 写 `debug.wav` 成功。
- Qwen3-TTS 输出波形存在越界警告。

处理：

`utils/tts_gen_sound.py` 已增加写 wav 前处理：

```text
torch tensor -> numpy
squeeze
float32
NaN/Inf 清理
clip 到 [-1, 1]
```

并增加兜底：

```text
soundfile 写临时 wav
如果 soundfile 失败，fallback 到 Python 标准库 wave 写 PCM16
最后替换为目标 wav
```

#### 10. TTS 成功后返回了宿主机路径，容器后续读不到

现象：

```text
视频生成服务提交失败: [Errno 2] No such file or directory:
/home/kemove/.../replace_speech/tts/<task_id>.wav
```

原因：

TTS 服务内部写的是宿主机映射路径，但返回给 celery-worker 的也是宿主机路径。后续 `comfyui-gateway` 在 Docker 容器里读不到 `/home/kemove/...`。

处理：

`tts_service.py` 改成：

- 内部写入时使用映射后的宿主机路径。
- API 响应里的 `tts_audio_path` 返回调用方传入的原始路径，也就是 `/app/metahuman_platform/...`。

这样后续 Docker 内服务可以继续读取同一个 bind mount 文件。

### 当前推荐启动顺序

1. 启动 ASR：

```bash
python -m uvicorn metahuman_platform.algorithm_services.asr_service:app --host 0.0.0.0 --port 7000
```

2. 启动 TTS：

```bash
BS_MEDIA_PATH_MAPPINGS=/app/metahuman_platform=/home/kemove/liwenmin/AI-Human/bs_media/.worktrees/main-release/function/remix_cut/metahuman_platform \
BS_MEDIA_QWEN3_TTS_ROOT=/home/kemove/zhouzhibiao/bs_media/function/remix_cut/Qwen3-TTS \
BS_MEDIA_QWEN3_TTS_MODEL=/home/kemove/zhouzhibiao/bs_media/function/remix_cut/Qwen3-TTS/Qwen3-TTS-12Hz-1.7B-Base \
python -m uvicorn metahuman_platform.algorithm_services.tts_service:app --host 0.0.0.0 --port 7001
```

3. 启动平台容器：

```bash
docker compose up -d --build web-api celery-worker comfyui-gateway
```

4. 提交换口播任务：

```bash
curl -X POST "http://localhost:7027/api/ai-transforms/tasks/upload-and-run" \
  -F "role_id=9fa94d55-46d8-4388-9ee5-85b33c459e08" \
  -F "source_video_id=080aaeb5-3f64-40e6-b3f1-633e9c0f9ac5" \
  -F 'operations=["replace_speech"]' \
  -F 'params={}' \
  -F "speech_text=大家好，这是新的测试口播内容。"
```

5. 查询任务：

```bash
curl "http://localhost:7027/api/ai-transforms/tasks/<task_id>"
```
