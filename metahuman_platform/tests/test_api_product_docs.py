import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_product_doc_upload_and_list_by_role(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": []},
            )
        ).json()

        upload = await client.post(
            f"/api/roles/{role['id']}/product-docs/upload",
            files={"file": ("product.txt", "商品卖点一\n商品卖点二".encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 200
        created = upload.json()
        assert created["name"] == "product.txt"
        assert "商品卖点一" in created["content"]

        listed = await client.get(f"/api/roles/{role['id']}/product-docs")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

        detail = await client.get(f"/api/product-docs/{created['id']}")
        assert detail.status_code == 200
        assert detail.json()["id"] == created["id"]


@pytest.mark.anyio
async def test_product_doc_upload_rejects_non_txt(tmp_path, monkeypatch):
    monkeypatch.setenv("BS_MEDIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BS_MEDIA_UPLOADS_DIR", str(tmp_path / "uploads"))

    async with app_client() as client:
        role = (
            await client.post(
                "/api/roles",
                json={"name": "角色A", "description": "", "tags": []},
            )
        ).json()

        upload = await client.post(
            f"/api/roles/{role['id']}/product-docs/upload",
            files={"file": ("product.md", b"# bad", "text/markdown")},
        )
        assert upload.status_code == 400
        assert upload.json()["error"]["message"] == "当前仅支持上传 txt 商品文档"
