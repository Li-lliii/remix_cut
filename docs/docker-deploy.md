# Docker 部署说明

## 一键启动

在服务器项目根目录执行：

```bash
./start
```

首次执行时会自动从 `.env.example` 复制生成 `.env`，然后执行：

```bash
docker compose up -d --build
```

停止服务：

```bash
./stop
```

## 会启动哪些容器

- `web-api`：FastAPI 平台服务，端口 `7028`
- `celery-worker`：AI 变身等异步任务 worker
- `comfyui-gateway`：平台调用 ComfyUI 的网关服务，端口 `7002`
- `rabbitmq`：Celery 消息队列
- `redis`：Celery result backend / 进度缓存
- `minio`：素材和生成结果对象存储
- `minio-init`：自动创建 MinIO bucket

## 需要手动确认的配置

### 1. `.env`

按服务器情况修改 MinIO 密码、ASR/TTS 地址等配置。

### 2. `config.yaml`

`comfyui-gateway` 会读取根目录 `config.yaml` 的 `comfyui` 配置。ComfyUI 本体通常单独部署在 GPU 机器上。

如果 ComfyUI 跑在宿主机：

```yaml
comfyui:
  server_address: "host.docker.internal:7040"
```

如果 ComfyUI 也放进同一个 compose 网络：

```yaml
comfyui:
  server_address: "comfyui:7040"
```

同时确认 `input_dir` 和 `output_dir` 对 gateway 容器可访问，必要时在 `docker-compose.yml` 里增加 volume 挂载。

## 访问地址

- 平台服务：http://服务器IP:7028
- MinIO 控制台：http://服务器IP:9001
- RabbitMQ 控制台：http://服务器IP:15672

## 注意

当前 `ai_transforms` 仓储仍使用 SQLite，并通过 `platform_data` volume 持久化。生产高并发前建议再迁 PostgreSQL。
