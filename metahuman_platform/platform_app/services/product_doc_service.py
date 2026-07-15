import shutil
from pathlib import Path

from platform_app.repositories.product_doc_repository import ProductDocRepository
from platform_app.repositories.role_repository import RoleRepository


class ProductDocService:
    def __init__(self, *, db_path: Path, uploads_dir: Path):
        self.db_path = Path(db_path)
        self.uploads_dir = Path(uploads_dir)
        self.role_repository = RoleRepository(self.db_path)
        self.product_doc_repository = ProductDocRepository(self.db_path)

    def list_role_docs(self, role_id: str):
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")
        return self.product_doc_repository.list_by_role(role_id)

    def get_doc(self, doc_id: str):
        doc = self.product_doc_repository.get(doc_id)
        if doc is None:
            raise ValueError("商品文档不存在")
        return doc

    def save_txt_doc(self, *, role_id: str, filename: str, file_stream) -> dict:
        if self.role_repository.get(role_id) is None:
            raise ValueError("角色不存在")
        suffix = Path(filename or "").suffix.lower()
        if suffix != ".txt":
            raise ValueError("当前仅支持上传 txt 商品文档")

        safe_name = Path(filename).name or "product_doc.txt"
        temp_dir = self.uploads_dir / "product_docs" / role_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / safe_name
        with temp_path.open("wb") as target:
            shutil.copyfileobj(file_stream, target)

        raw = temp_path.read_text(encoding="utf-8")
        content = raw.strip()
        if not content:
            temp_path.unlink(missing_ok=True)
            raise ValueError("商品文档内容不能为空")

        created = self.product_doc_repository.create(
            role_id=role_id,
            name=safe_name,
            file_path=str(temp_path.resolve()),
            content=content,
        )
        return created
