# 素材库模块说明

## 模块定位

`materials` 是统一素材资源池，用来管理上传过的视频、图片等资源。

当前已实现的分区：

```text
original_videos
background_images
```

`original_videos` 是原始视频分区，`background_images` 是背景图分区。上传后的文件会保存到 MinIO，并写入 `material_assets` 表。页面上的“我的资源/公共资源/素材管理”可以从这里读取。

## 目录结构

```text
platform_app/modules/materials/
├── api.py          # FastAPI 接口层
├── service.py      # 上传、查询、下载业务逻辑
├── repository.py   # material_assets 表读写
└── README.md
```

## 核心接口

### 上传原视频

```http
POST /api/materials/original-videos/upload
```

请求类型：

```text
multipart/form-data
```

字段：

```text
video: 视频文件
role_id: 可选，用于标记这个素材来自哪个角色
```

作用：

```text
接收上传文件
-> 临时写入本地 incoming 目录
-> 探测视频时长和宽高比例
-> 上传到 MinIO
-> 删除本地临时文件
-> 写 material_assets 表
-> 返回素材记录
```

MinIO key 格式：

```text
materials/original_videos/{material_asset_id}/source.mp4
```

数据库记录示例：

```text
asset_type = video
partition_name = original_videos
storage_backend = minio
storage_key = materials/original_videos/{id}/source.mp4
file_path = minio://bs-media/materials/original_videos/{id}/source.mp4
```

### 查询全部素材

```http
GET /api/materials
```

支持筛选：

```text
asset_type
partition_name
role_id
```

示例：

```http
GET /api/materials?asset_type=video&partition_name=original_videos
```

### 查询原视频素材

```http
GET /api/materials/original-videos
GET /api/materials/original-videos?role_id=xxx
```

作用：给素材管理页展示“我上传过的原视频”。

### 上传背景图

```http
POST /api/materials/background-images/upload
```

请求类型：

```text
multipart/form-data
```

字段：

```text
image: 背景图片
owner_user_id: 可选，当前用户 ID
visibility: private/public，默认 private
title: 可选，展示名称
tags: 可选，逗号分隔标签
```

我的资源背景图：

```text
visibility = private
source_type = user_upload
storage_key = materials/background_images/private/{owner_user_id}/{asset_id}/source.png
```

公共资源背景图：

```text
visibility = public
source_type = platform_builtin
storage_key = materials/background_images/public/platform/{asset_id}/source.png
```

### 查询背景图素材

```http
GET /api/materials/background-images?scope=mine&owner_user_id=xxx
GET /api/materials/background-images?scope=public
GET /api/materials/background-images?scope=available&owner_user_id=xxx
```

作用：

```text
mine      当前用户上传的私有背景图
public    平台上架的公共背景图
available 当前用户私有背景图 + 平台公共背景图
```

### 查询单个素材

```http
GET /api/materials/{asset_id}
```

作用：返回素材元数据。

### 预览/下载素材

```http
GET /api/materials/{asset_id}/stream
```

如果素材在 MinIO，接口返回 MinIO 预签名下载地址的重定向。

如果后续存在本地素材，接口会 fallback 为本地文件流。

## 数据表

### `material_assets`

统一素材表。

关键字段：

- `id`：素材 ID
- `asset_type`：素材类型，例如 `video`、`image`
- `partition_name`：分区名，例如 `original_videos`
- `source_type`：来源，例如 `user_upload`、`platform_builtin`
- `visibility`：可见性，例如 `private`、`public`
- `owner_user_id`：我的资源归属用户
- `owner_role_id`：可选，素材关联角色
- `title`：展示名称
- `filename`：原始文件名
- `file_path`：逻辑路径，MinIO 文件使用 `minio://bucket/key`
- `content_type`：文件 MIME 类型
- `storage_backend`：当前主要是 `minio`
- `storage_key`：MinIO object key
- `duration_sec`：视频时长
- `aspect_ratio`：视频比例
- `width`：图片宽度
- `height`：图片高度
- `tags_json`：标签
- `metadata_json`：扩展信息
- `status`：状态，当前默认 `active`
- `created_at`：创建时间
- `deleted_at`：软删除时间

## 和旧角色视频接口的关系

旧接口仍然存在：

```http
POST /api/roles/{role_id}/videos/upload
```

它现在底层也会调用素材库：

```text
上传角色视频
-> 存入 MinIO original_videos 分区
-> 写 material_assets
-> 再写 role_videos 兼容记录
```

`role_videos` 表新增了：

```text
material_asset_id
```

用于关联素材库里的原视频。

这样老页面和旧 API 还能继续使用，新素材管理页也能看到同一个视频。

## 和 ASR 的关系

素材库上传本身不应该强制 ASR。

但是旧角色视频上传接口仍然会触发 ASR，这是历史行为。由于视频现在在 MinIO，`VideoService.process_video_asr()` 会先把素材下载到本地 `_processing` 临时目录，再交给 ASR。

换背景不需要 ASR。

混剪、口播改写、文本总结等功能才需要 ASR。

## 和 AI 变身的关系

AI 变身模块通过 MinIO key 消费素材。

典型传参：

```json
{
  "input_asset_keys": {
    "source_video": "materials/original_videos/xxx/source.mp4",
    "background_image": "materials/background_images/yyy/source.png"
  }
}
```

当前已经支持背景图分区。AI 变身页面可以先查 `scope=available`，再让用户从“我的资源/公共资源”中选择背景图。

## 临时素材与长期素材

如果用户上传的视频/背景图要进入“我的资源”，应写入 `material_assets`。

如果素材只服务一次 AI 变身任务，不需要长期保存，可以后续设计临时分区：

```text
ai-transforms/tmp/{task_id}/source.mp4
ai-transforms/tmp/{task_id}/background.png
```

任务完成后清理临时输入，只保留结果视频。
