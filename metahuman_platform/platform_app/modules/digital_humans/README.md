# Digital Humans 模块技术架构

`digital_humans` 是数字人中心的后端功能模块，当前主要负责：

- 上传数字人训练素材，包括口播视频、人物图片、声音样本。
- 保存数字人基础信息、画像信息、素材记录、训练任务记录。
- 将大文件保存到 MinIO，将结构化业务数据保存到数据库。
- 提供数字人库列表接口，支持搜索、类型筛选、状态筛选和统计。
- 提供把数字人训练任务提交到 ComfyUI 的后端入口。

当前阶段的核心目标是先完成“数字人素材入库 + 数字人库展示 + 后台提交训练”的闭环。

## 分层结构

```text
用户 / 前端
  |
  v
api.py
  |
  v
service.py
  |
  +--> repository.py  -> SQLite / PostgreSQL
  +--> storage.py     -> MinIO
  +--> comfy_adapter.py
  +--> progress.py    -> Redis
  +--> tasks.py       -> Celery
```

### api.py

FastAPI 路由层。

职责：

- 定义 HTTP 接口。
- 读取 query、form、file、json 参数。
- 调用 `DigitalHumanService`。
- 将业务异常转换成 HTTP 错误。

这个文件不直接操作数据库，也不直接处理 MinIO 细节。

### service.py

业务编排层，是本模块的核心。

职责：

- 创建数字人。
- 创建数字人 profile。
- 保存上传素材。
- 创建训练任务。
- 组装数字人库列表返回结构。
- 按搜索、类型、状态筛选数字人。
- 将 MinIO 素材下载到本地临时目录后提交给 ComfyUI。

如果一个功能需要同时操作数据库、MinIO、ComfyUI、Redis，一般应该放在 `service.py` 编排。

### repository.py

数据访问层。

职责：

- 操作数字人相关数据库表。
- 屏蔽 SQLite / PostgreSQL 差异。
- 提供 create、get、list、update 等基础数据方法。

当前相关表：

- `digital_humans`：数字人主表，保存名称、类型、性别、状态、主展示素材。
- `digital_human_profiles`：数字人扩展资料，保存科室、机构、讲者、标签、简介。
- `digital_human_assets`：素材表，保存视频、图片、声音样本等文件的 MinIO key。
- `digital_human_generation_tasks`：生成/训练任务表，保存任务状态、workflow、ComfyUI job id、结果 key。

### storage.py

对象存储层。

职责：

- 上传素材到 MinIO。
- 生成预签名上传 URL。
- 检查 MinIO 对象是否存在。
- 生成下载 URL。
- 将 MinIO 对象下载到本地临时目录。

注意：视频、图片、音频这类大文件不直接存数据库，数据库只保存 MinIO 的 `storage_key`。

### comfy_adapter.py

ComfyUI 适配层。

职责：

- 把内部任务结构转换成 ComfyUI 需要的请求。
- 调用 ComfyUI。
- 返回后端任务 id，例如 `backend_job_id`。

后续真正接 ComfyUI workflow 时，主要扩展这里和 `service.py` 中的提交编排。

### progress.py

进度读写层。

职责：

- 从 Redis 读取任务进度。
- 写入任务进度。

当前数字人基础上传和列表展示主要依赖数据库；实时训练进度才需要 Redis。

### tasks.py

Celery 任务入口。

职责：

- 提供异步 worker 执行入口。
- 后续用于后台执行耗时生成任务、训练任务、后处理任务。

当前“上传数字人素材并创建训练任务”是同步完成的；真正训练可以后续通过后台任务触发。

### workflows.py

工作流执行层。

职责：

- 编排对象上传型任务。
- 下载输入素材。
- 调用生成器。
- 上传结果。
- 更新任务状态和进度。

目前更多用于换服装、换背景这类生成任务；数字人训练提交目前走 `submit_avatar_training_to_comfyui`。

## 存储设计

当前采用：

```text
数据库：保存结构化业务数据
MinIO：保存视频、图片、音频、生成结果等大文件
Redis：保存实时进度
Celery/RabbitMQ：执行异步任务
```

数字人上传后：

```text
digital_humans
  保存 name、avatar_type、gender、status

digital_human_profiles
  保存 department、organization、speaker_name、tags、description

digital_human_assets
  保存 talking_video / person_image / voice_sample 的 MinIO 信息

digital_human_generation_tasks
  保存 material_avatar_build 训练任务
```

素材记录示例：

```json
{
  "asset_type": "talking_video",
  "filename": "input_shot.mp4",
  "storage_backend": "minio",
  "storage_key": "digital-humans/{digital_human_id}/assets/talking_video.mp4",
  "file_path": "minio://bs-media/digital-humans/{digital_human_id}/assets/talking_video.mp4"
}
```

## 当前接口

### 1. 数字人库列表

```http
GET /api/digital-humans
```

作用：

- 给前端数字人库页面使用。
- 返回数字人卡片列表。
- 支持搜索、类型筛选、状态筛选。
- 返回统计信息，例如总数、已激活数量、训练中数量。

查询参数：

| 参数 | 说明 |
| --- | --- |
| `search` | 搜索关键词，匹配名称、科室、机构、讲者、标签、简介 |
| `keyword` | `search` 的兼容别名 |
| `avatar_type` | 按数字人类型筛选，例如 `real`、`anime` |
| `type` | `avatar_type` 的兼容别名 |
| `status` | 按状态筛选，支持 `active`、`training`、`failed` 或原始状态 |

示例：

```bash
curl "http://127.0.0.1:8000/api/digital-humans"
curl "http://127.0.0.1:8000/api/digital-humans?search=李"
curl "http://127.0.0.1:8000/api/digital-humans?avatar_type=real"
curl "http://127.0.0.1:8000/api/digital-humans?status=training"
```

返回结构核心字段：

```json
{
  "items": [
    {
      "id": "数字人ID",
      "name": "李医生",
      "avatar_type": "real",
      "status": "active",
      "status_group": "active",
      "status_label": "已激活",
      "department": "心内科",
      "description": "简介",
      "display_asset": {
        "id": "素材ID",
        "asset_type": "talking_video",
        "preview_url": "MinIO预签名下载地址"
      },
      "latest_task": {}
    }
  ],
  "total_count": 4,
  "filtered_count": 1,
  "summary": {
    "total_count": 4,
    "active_count": 3,
    "training_count": 1,
    "failed_count": 0
  },
  "filters": {
    "avatar_types": ["anime", "real"],
    "statuses": [
      {"value": "active", "label": "已激活"},
      {"value": "training", "label": "训练中"}
    ]
  }
}
```

### 2. 创建数字人训练素材

```http
POST /api/digital-humans/create-from-materials
POST /api/digital-humans/create-avatar
```

作用：

- 上传数字人基础信息和训练素材。
- 将基本信息写入数据库。
- 将视频、图片、声音样本上传到 MinIO。
- 创建一条 `material_avatar_build` 训练任务。

请求类型：

```text
multipart/form-data
```

表单字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 数字人名称 |
| `avatar_type` | 是 | 形象类型 |
| `department` | 是 | 科室/部门 |
| `gender` | 否 | 性别 |
| `organization` | 否 | 机构 |
| `speaker_name` | 否 | 主讲人 |
| `tags` | 否 | 标签，支持逗号分隔 |
| `style` | 否 | 风格 |
| `description` | 否 | 简介 |
| `talking_video` | 是 | 口播视频 |
| `person_image` | 否 | 人物图片 |
| `voice_sample` | 否 | 声音样本 |

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/digital-humans/create-from-materials \
  -F "name=测试数字人" \
  -F "avatar_type=real" \
  -F "department=测试部门" \
  -F "talking_video=@/Users/wm/test_video/input_shot.mp4;type=video/mp4"
```

返回内容：

- `digital_human`：数字人主表记录。
- `profile`：数字人资料记录。
- `assets`：素材记录。
- `generation_task`：训练任务记录。

### 3. 获取数字人详情

```http
GET /api/digital-humans/{digital_human_id}
```

作用：

- 查看单个数字人的完整信息。
- 返回基础信息、profile、素材列表、训练任务列表。

适合详情页、编辑页、调试任务状态使用。

### 4. 素材预览/下载

```http
GET /api/digital-humans/assets/{asset_id}/stream
```

作用：

- 根据素材 ID 访问文件。
- 如果素材在 MinIO，返回 MinIO 预签名下载地址的重定向。
- 如果素材在本地，直接返回文件流。

数字人库接口里的 `display_asset.preview_url` 已经会优先返回可预览地址，前端通常不需要手动拼这个接口。

### 5. 提交数字人训练到 ComfyUI

```http
POST /api/digital-humans/generation-tasks/{task_id}/submit-comfyui
```

作用：

- 将 `material_avatar_build` 任务提交到 ComfyUI。
- 从 MinIO 下载素材到本地临时目录。
- 调用 `DigitalHumanComfyAdapter`。
- 将 ComfyUI 返回的任务 ID 保存到 `backend_job_id`。
- 将任务状态更新为 `submitted`。

适合后台管理端或任务调度器调用。

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/digital-humans/generation-tasks/{task_id}/submit-comfyui
```

### 6. 查询训练/生成任务

```http
GET /api/digital-humans/generation-tasks/{task_id}
```

作用：

- 查询任务数据库状态。
- 查询 Redis 中的实时进度。
- 如果任务已有结果文件，返回结果下载 URL。

返回内容：

- `task`：数据库任务记录。
- `progress`：Redis 进度。
- `result_download_url`：结果文件下载地址。

### 7. 创建对象上传型任务

```http
POST /api/digital-humans/object-upload-tasks
```

作用：

- 创建一个需要前端直传素材到 MinIO 的任务。
- 后端生成 MinIO 预签名上传 URL。
- 前端拿 URL 直接上传文件。

这个接口更适合换服装、换背景等多素材生成任务；当前数字人训练上传主流程暂时不依赖它。

### 8. 提交对象上传型任务

```http
POST /api/digital-humans/generation-tasks/submit
```

作用：

- 检查对象上传型任务的素材是否已经上传到 MinIO。
- 将素材登记到 `digital_human_assets`。
- 将任务状态更新为 `queued`。
- 投递 Celery 异步任务。

### 9. 换服装任务

```http
POST /api/digital-humans/{digital_human_id}/outfit-change-tasks
```

作用：

- 创建数字人换服装任务。
- 生成源视频和服装图的 MinIO 预签名上传 URL。

当前属于后续扩展功能，不是数字人训练主流程。

### 10. 换背景任务

```http
POST /api/digital-humans/{digital_human_id}/background-change-tasks
```

作用：

- 创建数字人换背景任务。
- 生成源视频和背景图的 MinIO 预签名上传 URL。

当前属于后续扩展功能，不是数字人训练主流程。

## 状态设计

数字人主表 `digital_humans.status` 当前会被归类为前端展示状态：

| 原始状态 | 展示分组 | 展示文案 |
| --- | --- | --- |
| `active` / `success` / `completed` | `active` | 已激活 |
| `training_pending` / `pending` / `queued` / `submitted` / `running` / `training` | `training` | 训练中 |
| `failed` / `cancelled` | `failed` | 失败 |
| `draft` | `draft` | 草稿 |

数字人上传后默认是：

```text
digital_humans.status = training_pending
generation_task.status = pending
```

提交到 ComfyUI 后：

```text
generation_task.status = submitted
generation_task.backend_job_id = ComfyUI 返回的任务ID
```

后续训练完成后，需要再补充 worker 或回调逻辑，把数字人状态更新为 `active`，并设置可展示的主素材。

## 测试

当前数字人模块测试位于：

```text
metahuman_platform/tests/digital_humans/
```

库展示接口测试：

```text
test_library_api.py
```

覆盖内容：

- `GET /api/digital-humans` 列表。
- `search` 搜索。
- `avatar_type` / `type` 类型筛选。
- `status=active` / `status=training` 状态筛选。
- `summary.active_count`、`summary.training_count` 统计。
- `display_asset.preview_url` 展示素材地址。

运行：

```bash
BS_MEDIA_PLATFORM_LOG_FILE=/tmp/bs-media-platform-test.log \
.venv/bin/python -m pytest metahuman_platform/tests/digital_humans -q
```

## 后续扩展建议

如果继续扩展数字人中心，可以按功能逐步拆分：

```text
modules/digital_humans/
  api.py
  service.py
  repository.py
  storage.py
  comfy_adapter.py
  progress.py
  tasks.py
  workflows.py
```

当前文件数量还不算失控，可以先保持这一层。等功能继续增多后，再拆成：

```text
modules/digital_humans/
  api/
    library.py
    training.py
    generation.py
  services/
    library_service.py
    training_service.py
    generation_service.py
  repositories/
    digital_human_repository.py
    asset_repository.py
    task_repository.py
  integrations/
    minio_storage.py
    comfy_adapter.py
    redis_progress.py
```

拆分时机：

- 单个文件超过 400-600 行。
- 列表、训练、换装、换背景之间的逻辑开始互相干扰。
- 不同功能需要不同开发人员并行维护。
- 测试文件开始难以定位具体功能。

当前建议先继续保持模块内单层文件结构，等数字人训练闭环跑通后再做二级目录拆分。
