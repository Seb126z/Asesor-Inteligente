import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.common import student_scope
from app.api.deps import get_current_user
from app.core.config import MAX_UPLOAD_MB
from app.core.database import get_db
from app.models.entities import Evidence, Laboratory, User
from app.services.evidence_store import read_evidence_bytes
from app.services.evidence_text import extract_text_from_bytes

router = APIRouter(tags=["evidencias"])
ALLOWED_EXTENSIONS = {".pdf", ".zip", ".txt", ".py", ".js", ".html", ".docx",
                      ".pptx", ".png", ".jpg", ".jpeg", ".mp4"}
CODE_SUFFIXES = (".py", ".js", ".java", ".cpp", ".txt", ".json", ".html", ".sql")


def analyze_upload(data: bytes, name: str) -> dict:
    """Resumen rápido del archivo recién subido (no extrae nada al disco)."""
    suffix = Path(name).suffix.lower()
    if suffix in {".pdf", ".txt", ".py", ".js", ".html"}:
        preview, readable = extract_text_from_bytes(data, name)
        return {"readable": readable, "total_characters": len(preview) if readable else 0,
                "preview": preview[:600] if readable else None}
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
        except zipfile.BadZipFile:
            return {"error": "El ZIP está dañado o no es válido"}
        code = [n for n in names if n.lower().endswith(CODE_SUFFIXES)]
        return {"total_files": len(names), "code_files_found": code[:50]}
    return {}


@router.post("/laboratories/{laboratory_id}/evidence")
async def upload_evidence(laboratory_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    if not db.get(Laboratory, laboratory_id):
        raise HTTPException(404, "Laboratorio no encontrado")
    safe_name = Path(file.filename or "evidencia.bin").name
    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Tipo de archivo no permitido")

    limit = MAX_UPLOAD_MB * 1024 * 1024
    buffer = bytearray()
    try:
        while chunk := await file.read(1024 * 1024):
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise HTTPException(413, f"El archivo supera {MAX_UPLOAD_MB} MB")
    finally:
        await file.close()
    if not buffer:
        raise HTTPException(422, "El archivo está vacío")

    data = bytes(buffer)
    record = Evidence(laboratory_id=laboratory_id, student=user.name, student_id=user.id,
                      original_name=safe_name, stored_name=f"{uuid4().hex}_{safe_name}",
                      content_type=file.content_type or "application/octet-stream",
                      size_bytes=len(data), content=data)
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "laboratory_id": laboratory_id, "filename": record.original_name,
            "size_bytes": len(data), "message": "Evidencia almacenada",
            "file_analysis": analyze_upload(data, safe_name)}


@router.get("/laboratories/{laboratory_id}/evidence")
def list_evidence(laboratory_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not db.get(Laboratory, laboratory_id):
        raise HTTPException(404, "Laboratorio no encontrado")
    query = db.query(Evidence).filter(Evidence.laboratory_id == laboratory_id)
    scope = student_scope(user)
    if scope is not None:
        query = query.filter(Evidence.student_id == scope)
    return query.order_by(Evidence.uploaded_at.desc()).all()


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(Evidence, evidence_id)
    scope = student_scope(user)
    if not record or (scope is not None and record.student_id != scope):
        raise HTTPException(404, "Evidencia no encontrada")
    data = read_evidence_bytes(record)
    if data is None:
        raise HTTPException(404, "Archivo no disponible")
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.original_name)}"})
