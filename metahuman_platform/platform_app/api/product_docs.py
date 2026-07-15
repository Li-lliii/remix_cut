from fastapi import APIRouter, File, HTTPException, UploadFile

from platform_app.services.product_doc_service import ProductDocService
from platform_app.settings import get_settings


router = APIRouter(tags=["product-docs"])


def build_product_doc_service():
    settings = get_settings()
    return ProductDocService(
        db_path=settings.database_path,
        uploads_dir=settings.uploads_dir,
    )


@router.get("/api/roles/{role_id}/product-docs")
async def list_role_product_docs(role_id: str):
    try:
        return {"items": build_product_doc_service().list_role_docs(role_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/roles/{role_id}/product-docs/upload")
async def upload_role_product_doc(role_id: str, file: UploadFile = File(...)):
    try:
        created = build_product_doc_service().save_txt_doc(
            role_id=role_id,
            filename=file.filename or "product_doc.txt",
            file_stream=file.file,
        )
        return created
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/product-docs/{doc_id}")
async def get_product_doc(doc_id: str):
    try:
        return build_product_doc_service().get_doc(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
