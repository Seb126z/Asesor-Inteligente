"""Agrega los routers de la API bajo el prefijo /api."""
from fastapi import APIRouter

from app.api import analytics, evaluations, evidence, laboratories

router = APIRouter(prefix="/api")


@router.get("/health", tags=["sistema"])
def health():
    return {"status": "ok", "service": "asesor-pedagogico-api"}


for module in (laboratories, evidence, evaluations, analytics):
    router.include_router(module.router)
