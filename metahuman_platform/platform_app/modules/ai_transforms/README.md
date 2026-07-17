# AI 变身模块说明

## 模块定位

`ai_transforms` 用来承载“AI 变身”类长任务，例如：

- 换背景：`replace_background`
- 换产品：预留
- 换服装/AI 换装：预留
- 换数字人：预留
- 换口播：预留

当前代码已经真实接入的是 `replace_background`。它会把原视频和背景图交给 ComfyUI 工作流生成新视频。

## 目录结构

```text
platform_app/modules/ai_transforms/
├── api.py            # FastAPI 接口层
├── schemas.py        # 请求参数模型和支持能力枚举
├── service.py        # 业务编排：校验、建任务、投递 Celery
├── repository.py     # SQLite 任务表读写
├── tasks.py          # Celery 任务入口
├── workflows.py      # 后台执行器：下载素材、调 ComfyUI、上传结果
├── comfy_adapter.py  # 调用 ComfyUI gateway
├── storage.py        # MinIO 输入/结果存储封装
└── README.md
```

## 核心接口

### 创建任务

```http
POST /api/ai-transforms/tasks
```

作用：创建 AI 变身任务，但不一定立即执行。当前只允许：

```json
{
  "operations": ["replace_background"]
}
```

典型请求：

```json
{
  "role_id": "角色ID",
  "source_video_id": "原视频记录ID",
  "operations": ["replace_background"],
  "input_asset_keys": {
    "source_video": "materials/original_videos/private/user_1/xxx/source.mp4",
    "background_image": "materials/background_images/public/platform/yyy/source.png"
  },
  "params": {}
}
```

当前 `input_asset_keys` 要求传 MinIO object key。`service.py` 会检查这些 key 是否存在。

背景图可以来自素材库的“我的资源”或“公共资源”。当前任务层消费的是 MinIO key，后续可以升级为前端传 `asset_id`，后端再解析权限和 `storage_key`。

### 提交任务

```http
POST /api/ai-transforms/tasks/submit
```

作用：把已创建的任务投递给 Celery。

请求：

```json
{
  "task_id": "任务ID"
}
```

成功后任务状态变为 `queued`。

### 查询任务

```http
GET /api/ai-transforms/tasks/{task_id}
```

作用：查询主任务、子任务和结果下载地址。

返回结构包含：

- `task`：主任务记录
- `items`：每个 operation 对应的子任务
- `result_download_url`：结果视频预签名下载地址

### 任务列表

```http
GET /api/ai-transforms/tasks
GET /api/ai-transforms/tasks?role_id=xxx
```

作用：查询当前已有 AI 变身任务。

### 取消任务

```http
POST /api/ai-transforms/tasks/{task_id}/cancel
```

作用：把未完成任务标记为 `cancelled`。

### 删除任务记录

```http
DELETE /api/ai-transforms/tasks/{task_id}?role_id=xxx
```

作用：软删除任务记录。

## 数据表

### `ai_transform_tasks`

主任务表，记录一次“一键变身”。

关键字段：

- `id`：任务 ID
- `role_id`：所属角色
- `source_video_id`：原视频记录 ID
- `status`：任务状态
- `operations_json`：选择的能力数组
- `input_asset_keys_json`：输入素材 MinIO key
- `params_json`：扩展参数
- `output_key`：结果视频 MinIO key
- `error_message`：错误信息

### `ai_transform_task_items`

子任务表，一次主任务里每个能力对应一条子任务。

当前只有：

```text
replace_background
```

未来多选时可以扩展为：

```text
replace_background -> replace_clothes -> replace_speech
```

## 当前换背景工作流

ComfyUI workflow 文件：

```text
workstream/ai_transforms/replace_background_api.json
```

这是 ComfyUI API workflow 格式。`scripts/run_comfyui_workflow.py` 会读取它，替换输入视频、背景图和输出前缀，然后提交给 ComfyUI `/prompt`。

当前默认节点映射在 `comfy_adapter.py`：

```python
{
    "178.inputs.video": "{video}",
    "225.inputs.image": "{background_image}",
    "176.inputs.filename_prefix": "{filename_prefix}",
    "176.inputs.save_output": True,
}
```

含义：

- `178`：原视频输入节点，`VHS_LoadVideo`
- `225`：背景图输入节点，`LoadImage`
- `176`：最终视频输出节点，`VHS_VideoCombine`

## 执行流程

```text
前端创建任务
-> service.py 校验 role/video/input keys
-> repository.py 写 ai_transform_tasks 和 ai_transform_task_items
-> 前端提交任务
-> tasks.py 投递 Celery
-> workflows.py 下载 MinIO 输入到本地 temp
-> comfy_adapter.py 提交 ComfyUI gateway
-> ComfyUI 生成结果
-> workflows.py 上传结果到 MinIO
-> SQLite 回写 success/output_key
-> 前端轮询拿 result_download_url
```

## 和素材库的关系

AI 变身模块不负责“上传素材”。它只消费素材 key。

素材来源可以有两类：

1. 素材库长期素材  
   例如 `materials/original_videos/private/{owner}/{asset_id}/...` 和 `materials/background_images/public/platform/{asset_id}/...`。

2. 临时任务素材  
   后续可扩展为 `ai-transforms/tmp/{task_id}/...`。

当前代码里，AI 变身任务通过 `input_asset_keys` 使用已经存在于 MinIO 的原视频和背景图。

## 后续建议

- 新增背景图素材上传接口：`/api/materials/background-images/upload`
- 新增一键上传并运行接口：`/api/ai-transforms/tasks/upload-and-run`
- 支持 `auto_submit=true`
- 支持多 operation 串行执行
- 把 SQLite 迁移到 PostgreSQL，以支持多 worker 高并发



核心路线如下：
前端
  |
  v
api.py              接收 HTTP 请求
  |
  v
service.py          编排业务流程
  |
  +--> repository.py     写数据库
  +--> storage.py        写 MinIO / 生成下载地址
  +--> comfy_adapter.py  提交 ComfyUI
  +--> progress.py       读写 Redis 进度
  +--> tasks.py          Celery 后台任务入口
当前数字人模块的主流程是：
1. 前端上传数字人基础信息 + 视频素材
2. api.py 接收 multipart/form-data
3. service.py 校验参数并编排创建流程
4. repository.py 写入：
   - digital_humans
   - digital_human_profiles
   - digital_human_assets
   - digital_human_generation_tasks
5. storage.py 把视频文件上传到 MinIO
6. 数据库只保存 MinIO 的 storage_key，不保存视频二进制
7. 后台或管理端调用 submit-comfyui 接口
8. service.py 从 MinIO 下载素材到本地临时目录
9. comfy_adapter.py 提交给 ComfyUI
10. 数据库记录 backend_job_id 和任务状态
数字人库展示的路线是：
GET /api/digital-humans
  |
  v
api.py 读取 search / avatar_type / status
  |
  v
service.py 查询数字人、profile、素材、任务
  |
  v
组装成前端卡片需要的数据
  |
  v
返回 items + summary + filters
这个新模式的好处是：
api.py 只管接口，不写业务细节。
service.py 负责业务编排，是功能主入口。
repository.py 只管数据库，后续 SQLite 切 PostgreSQL 时影响更小。
storage.py 只管 MinIO，文件存储逻辑不会散落在接口里。
comfy_adapter.py 只管 ComfyUI，对接算法服务时更清晰。
tasks.py / progress.py 为后续异步训练、实时进度预留
FastAPI + MinIO + PostgreSQL/SQLite + RabbitMQ + Celery + ComfyUI HTTP API
FastAPI
  接收请求

PostgreSQL / SQLite
  存数字人、素材记录、任务记录

MinIO
  存视频、图片、音频、生成结果

RabbitMQ
  存待执行任务消息

Celery
  执行后台任务

Redis
  存实时进度

ComfyUI
  执行 AI 生成