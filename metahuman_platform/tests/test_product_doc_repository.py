from platform_app.db import init_db
from platform_app.repositories.product_doc_repository import ProductDocRepository
from platform_app.repositories.role_repository import RoleRepository


def test_product_doc_repository_create_and_list_by_role(tmp_path):
    db_path = tmp_path / "app.db"
    init_db(db_path)

    role_repo = RoleRepository(db_path)
    repository = ProductDocRepository(db_path)

    role = role_repo.create(name="角色A", description="", tags=[], avatar_url="")
    created = repository.create(
        role_id=role["id"],
        name="商品说明.txt",
        file_path=str((tmp_path / "doc.txt").resolve()),
        content="这里是商品说明",
    )

    assert created["role_id"] == role["id"]
    assert created["content"] == "这里是商品说明"

    items = repository.list_by_role(role["id"])
    assert len(items) == 1
    assert items[0]["id"] == created["id"]
    assert repository.get(created["id"])["name"] == "商品说明.txt"
