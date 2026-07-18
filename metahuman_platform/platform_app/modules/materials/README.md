# 素材库模块说明

## 模块定位

`materials` 是创建数字人前的素材管理池，用来管理可被创建流程选择的视频、图片、音频。

素材在这里还不属于某个数字人。用户创建数字人时可以选择：

```text
本地上传 -> 直接写入 digital_human_assets
平台上传 -> 从 material_assets 选择素材，再登记到 digital_human_assets
```

创建完成后，被选中的平台素材会成为该数字人下面的正式资产，并在 `digital_human_assets.metadata_json` 中记录来源素材 ID。

当前分区：

```text
digital_human_creation  创建数字人素材池，支持 video/image/audio
original_videos         旧角色视频兼容分区
background_images       旧背景图/AI 变身兼容分区
```

## 目录结构

```text
platform_app/modules/materials/
├── api.py          # FastAPI 接口层
├── constants.py    # 素材类型、分区、可见性常量
├── service.py      # 上传、查询、下载业务逻辑
├── repository.py   # material_assets 表读写
└── README.md
```

## 创建数字人素材接口

### 上传视频素材

```http
POST /api/materials/digital-human/videos/upload
```

字段：

```text
video: 视频文件
owner_user_id: 可选，当前用户 ID
visibility: private/public，默认 private
title: 可选，展示名称
tags: 可选，逗号分隔标签
```

返回：单条 `material_assets` 记录。

```text
asset_type = video
partition_name = digital_human_creation
storage_key = materials/digital_human_creation/video/{visibility}/{owner}/{asset_id}/source.mp4
```

### 上传图片素材

```http
POST /api/materials/digital-human/images/upload
```

字段：

```text
image: 图片文件
owner_user_id: 可选
visibility: private/public，默认 private
title: 可选
tags: 可选
```

返回：单条 `material_assets` 记录。

```text
asset_type = image
partition_name = digital_human_creation
storage_key = materials/digital_human_creation/image/{visibility}/{owner}/{asset_id}/source.png
```

### 上传音频素材

```http
POST /api/materials/digital-human/audios/upload
```

字段：

```text
audio: 音频文件
owner_user_id: 可选
visibility: private/public，默认 private
title: 可选
tags: 可选
```

返回：单条 `material_assets` 记录。

```text
asset_type = audio
partition_name = digital_human_creation
storage_key = materials/digital_human_creation/audio/{visibility}/{owner}/{asset_id}/source.mp3
```

### 查询素材池

```http
GET /api/materials/digital-human/videos?scope=available&owner_user_id=xxx
GET /api/materials/digital-human/images?scope=available&owner_user_id=xxx
GET /api/materials/digital-human/audios?scope=available&owner_user_id=xxx
```

`scope` 支持：

```text
mine       当前用户私有素材
public     平台公共素材
available  当前用户私有素材 + 平台公共素材
```

返回：

```json
{
  "items": [
    {
      "id": "素材ID",
      "asset_type": "video",
      "partition_name": "digital_human_creation",
      "visibility": "private",
      "owner_user_id": "user-1",
      "title": "训练视频",
      "filename": "talk.mp4",
      "file_path": "minio://bs-media/materials/digital_human_creation/video/private/user-1/...",
      "storage_backend": "minio",
      "storage_key": "materials/digital_human_creation/video/private/user-1/...",
      "metadata_json": {
        "source": "digital_human_material_upload"
      }
    }
  ]
}
```

## 创建数字人时使用平台素材

创建数字人接口支持本地上传和素材库选择两种方式：

```http
POST /api/digital-humans/create-from-materials
```

本地上传字段：

```text
talking_video
person_image
voice_sample
```

平台素材字段：

```text
talking_video_material_id
person_image_material_id
voice_sample_material_id
```

规则：

```text
talking_video 或 talking_video_material_id 必填
person_image/person_image_material_id 可选
voice_sample/voice_sample_material_id 可选
```

如果传平台素材 ID，后端会：

```text
查 material_assets
-> 校验 partition_name = digital_human_creation
-> 校验 asset_type 匹配 video/image/audio
-> 写 digital_human_assets
-> metadata_json 记录 source_material_asset_id
```

素材文件本身不会重复上传，`digital_human_assets.storage_key` 会引用同一个 MinIO object key。

## 通用素材接口

### 查询全部素材

```http
GET /api/materials
```

支持筛选：

```text
asset_type
partition_name
role_id
owner_user_id
scope
```

### 查询单个素材

```http
GET /api/materials/{asset_id}
```

返回素材元数据。

### 预览/下载素材

```http
GET /api/materials/{asset_id}/stream
```

如果素材在 MinIO，返回 MinIO 预签名下载地址的重定向。如果素材在本地，返回文件流。

## 兼容接口

旧角色视频接口仍然存在：

```http
POST /api/materials/original-videos/upload
GET /api/materials/original-videos
```

它们继续使用 `original_videos` 分区，供旧角色视频上传和 ASR 链路使用。

背景图兼容接口仍然存在：

```http
POST /api/materials/background-images/upload
GET /api/materials/background-images
```

它们继续使用 `background_images` 分区，供已有背景图/AI 变身页面使用。

## 数据表

### `material_assets`

统一素材表。

关键字段：

- `id`：素材 ID
- `asset_type`：素材类型，`video`、`image`、`audio`
- `partition_name`：分区名，例如 `digital_human_creation`
- `source_type`：来源，例如 `user_upload`、`platform_builtin`
- `visibility`：可见性，例如 `private`、`public`
- `owner_user_id`：素材归属用户
- `owner_role_id`：旧角色视频兼容字段
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
