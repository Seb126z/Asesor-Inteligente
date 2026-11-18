"""Acceso al contenido de las evidencias.

Las evidencias nuevas se guardan en la base de datos (columna `content`). Las antiguas, subidas cuando los
archivos iban a disco, se siguen leyendo desde UPLOAD_DIR si el archivo todavía existe.
"""
from app.core.config import UPLOAD_DIR
from app.models.entities import Evidence


def read_evidence_bytes(record: Evidence) -> bytes | None:
    if record.content is not None:
        return bytes(record.content)
    legacy = (UPLOAD_DIR / record.stored_name).resolve()
    if legacy.is_relative_to(UPLOAD_DIR.resolve()) and legacy.is_file():
        return legacy.read_bytes()
    return None
