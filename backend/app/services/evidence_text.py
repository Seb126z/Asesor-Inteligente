"""Extracción de texto de evidencias para el evaluador.

Soporta texto plano/código y PDF con capa de texto (vía pypdf). Los PDF escaneados (solo imagen),
DOCX, ZIP, etc. siguen pendientes: en esos casos se informa que no hay texto en lugar de inventar contenido.
"""
import io
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".py", ".js", ".html", ".md", ".csv", ".json"}
MAX_CHARS = 20_000
MAX_PDF_PAGES = 60


def _read_pdf(source) -> str:
    """`source` puede ser una ruta o un flujo en memoria."""
    from pypdf import PdfReader

    reader = PdfReader(source)
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return ""
        except Exception:
            return ""
    parts, total = [], 0
    for number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            continue
        if text:
            parts.append(f"--- Página {number} ---\n{text}")
            total += len(text)
        if total >= MAX_CHARS:
            break
    return "\n".join(parts)[:MAX_CHARS]


def extract_text_from_bytes(data: bytes, original_name: str) -> tuple[str, bool]:
    """Devuelve (texto, se_extrajo_contenido)."""
    suffix = Path(original_name).suffix.lower()
    if data:
        if suffix in TEXT_SUFFIXES:
            text = data[: MAX_CHARS * 4].decode("utf-8", errors="replace")[:MAX_CHARS]
            if text.strip():
                return text, True
        elif suffix == ".pdf":
            try:
                text = _read_pdf(io.BytesIO(data))
            except ImportError:
                return ("[Falta instalar la librería pypdf en el servidor: ejecuta "
                        "`pip install -r requirements.txt` y reinicia el servidor.]"), False
            except Exception:
                text = ""
            if text.strip():
                return text, True
            return (f"[El PDF '{original_name}' no tiene texto seleccionable: parece un escaneo o una imagen "
                    "(o está dañado/protegido). Expórtalo de nuevo como PDF con texto, o sube un .txt.]"), False
    return (f"[Archivo '{original_name}': no se pudo extraer texto de este tipo de archivo. "
            "No hay contenido para evaluar.]"), False


def extract_text(path: Path, original_name: str) -> tuple[str, bool]:
    """Versión para archivos en disco (se conserva por compatibilidad y para pruebas)."""
    data = path.read_bytes() if path.is_file() else b""
    return extract_text_from_bytes(data, original_name)
