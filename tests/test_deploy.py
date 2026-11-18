"""Preparación para despliegue: Neon, archivos en la base de datos, cabeceras y CORS."""
import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def reload_config(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import app.core.config as config
    return importlib.reload(config)


@pytest.fixture(autouse=True)
def restore_config():
    yield
    import app.core.config as config
    importlib.reload(config)


def test_url_de_neon_agrega_ssl_y_usa_psycopg2(monkeypatch):
    cfg = reload_config(monkeypatch, DATABASE_URL="postgresql://u:clave@ep-cool-123-pooler.us-east-2.aws.neon.tech/neondb")
    url = make_url(cfg.DATABASE_URL)
    assert url.drivername == "postgresql+psycopg2" and url.query["sslmode"] == "require"


def test_url_de_neon_conserva_parametros_existentes(monkeypatch):
    original = "postgresql://u:clave@ep-x-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    cfg = reload_config(monkeypatch, DATABASE_URL=original)
    q = make_url(cfg.DATABASE_URL).query
    assert q["sslmode"] == "require" and q["channel_binding"] == "require"


def test_url_con_comillas_y_arroba_en_la_clave(monkeypatch):
    cfg = reload_config(monkeypatch, DATABASE_URL='  "postgres://u:cl@ve#1@ep-a.neon.tech/neondb"  ')
    url = make_url(cfg.DATABASE_URL)
    assert url.password == "cl@ve#1" and url.host == "ep-a.neon.tech"


def test_produccion_cierra_cors_y_exige_jwt(monkeypatch):
    cfg = reload_config(monkeypatch, APP_ENV="production", JWT_SECRET="x" * 40)
    assert cfg.CORS_ORIGINS == []
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(RuntimeError):
        importlib.reload(cfg)


def test_cabeceras_de_seguridad(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_evidencia_se_guarda_en_la_base_y_no_en_disco(client):
    login = client.post("/api/auth/login", data={"username": "estudiante@demo.local", "password": "estudiante123"}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    r = client.post("/api/laboratories/1/evidence", headers=h, files={"file": ("nota.txt", "contenido ñandú".encode(), "text/plain")})
    assert r.status_code == 200
    ev_id = r.json()["id"]
    listado = client.get("/api/laboratories/1/evidence", headers=h).json()
    item = next(e for e in listado if e["id"] == ev_id)
    assert item["size_bytes"] == len("contenido ñandú".encode()) and "content" not in item
    descarga = client.get(f"/api/evidence/{ev_id}/download", headers=h)
    assert descarga.content.decode() == "contenido ñandú"
    assert "nota.txt" in descarga.headers["content-disposition"]
    upload_dir = Path(os.environ["UPLOAD_DIR"])
    assert not upload_dir.exists() or not any(upload_dir.iterdir())


def test_archivo_vacio_se_rechaza(client):
    login = client.post("/api/auth/login", data={"username": "estudiante@demo.local", "password": "estudiante123"}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    assert client.post("/api/laboratories/1/evidence", headers=h, files={"file": ("v.txt", b"", "text/plain")}).status_code == 422
