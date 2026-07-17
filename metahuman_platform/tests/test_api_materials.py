from __future__ import annotations

import pytest

from conftest import app_client


class FakeMinioObjectStorage:
    objects = {}

    def __init__(self, *args, **kwargs):
        del args, kwargs

    def upload_file(self, object_key, source_path, *, content_type="application/octet-stream"):
        del content_type
        self.objects[object_key] = source_path.read_bytes()
        return object_key

    def presigned_get_url(self, object_key):
        return f"https://minio.test/{object_key}"

    def download_file(self, object_key, target_path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(self.objects[object_key])
        return target_path


@pytest.mark.anyio
async def test_role_video_upload_is_saved_to_original_video_material_partition(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "素材角色", "description": "", "tags": []},
            )
        ).json()

        uploaded = await client.post(
            f"/api/roles/{role['id']}/videos/upload",
            files={"video": ("source.mp4", b"fake-video", "video/mp4")},
        )
        materials = await client.get("/api/materials/original-videos", params={"role_id": role["id"]})

    assert uploaded.status_code == 200
    video = uploaded.json()
    assert video["material_asset_id"]
    assert video["file_path"].startswith("minio://bs-media/materials/original_videos/")

    assert materials.status_code == 200
    items = materials.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == video["material_asset_id"]
    assert items[0]["partition_name"] == "original_videos"
    assert items[0]["asset_type"] == "video"
    assert items[0]["storage_backend"] == "minio"
    assert items[0]["storage_key"].startswith("materials/original_videos/")


@pytest.mark.anyio
async def test_upload_original_video_material_and_stream(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)

    async with app_client() as client:
        uploaded = await client.post(
            "/api/materials/original-videos/upload",
            files={"video": ("standalone.mp4", b"standalone-video", "video/mp4")},
        )
        asset_id = uploaded.json()["id"]
        streamed = await client.get(f"/api/materials/{asset_id}/stream", follow_redirects=False)

    assert uploaded.status_code == 200
    asset = uploaded.json()
    assert asset["partition_name"] == "original_videos"
    assert asset["filename"] == "standalone.mp4"
    assert asset["storage_backend"] == "minio"
    assert asset["storage_key"] in FakeMinioObjectStorage.objects
    assert streamed.status_code in {302, 307}
    assert streamed.headers["location"] == f"https://minio.test/{asset['storage_key']}"


@pytest.mark.anyio
async def test_background_images_support_mine_public_and_available_scopes(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("BS_MEDIA_DEFAULT_ASR_MODE", "mock")
    monkeypatch.setattr("platform_app.modules.materials.service.MinioObjectStorage", FakeMinioObjectStorage)

    async with app_client() as client:
        mine = await client.post(
            "/api/materials/background-images/upload",
            params={"owner_user_id": "user-1", "title": "我的背景", "tags": "直播间,简洁"},
            files={"image": ("mine.png", b"fake-image", "image/png")},
        )
        public = await client.post(
            "/api/materials/background-images/upload",
            params={"visibility": "public", "title": "公共背景"},
            files={"image": ("public.png", b"fake-public-image", "image/png")},
        )
        mine_list = await client.get(
            "/api/materials/background-images",
            params={"scope": "mine", "owner_user_id": "user-1"},
        )
        public_list = await client.get("/api/materials/background-images", params={"scope": "public"})
        available = await client.get(
            "/api/materials/background-images",
            params={"scope": "available", "owner_user_id": "user-1"},
        )

    assert mine.status_code == 200
    assert public.status_code == 200
    mine_asset = mine.json()
    public_asset = public.json()
    assert mine_asset["visibility"] == "private"
    assert mine_asset["source_type"] == "user_upload"
    assert mine_asset["owner_user_id"] == "user-1"
    assert mine_asset["storage_key"].startswith("materials/background_images/private/user-1/")
    assert mine_asset["tags_json"] == ["直播间", "简洁"]
    assert public_asset["visibility"] == "public"
    assert public_asset["source_type"] == "platform_builtin"
    assert public_asset["storage_key"].startswith("materials/background_images/public/platform/")

    assert [item["id"] for item in mine_list.json()["items"]] == [mine_asset["id"]]
    assert [item["id"] for item in public_list.json()["items"]] == [public_asset["id"]]
    assert {item["id"] for item in available.json()["items"]} == {mine_asset["id"], public_asset["id"]}
