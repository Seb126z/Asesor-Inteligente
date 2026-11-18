from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import APP_NAME, CORS_ORIGINS
from app.core.database import SessionLocal, ensure_schema
from app.models.entities import Laboratory
from app.api.routes import router
from app.api.auth import router as auth_router
from app.services.users import seed_users


SEED = [
 (1,1,"Lab 1 · Búsqueda y agentes",["busqueda","agentes"],[{"name":"Algoritmo de búsqueda","weight":40,"indicators":["bfs","a*","heurística","nodos"]},{"name":"Diseño del agente","weight":30,"indicators":["agente","percepción","acción","entorno"]},{"name":"Análisis de resultados","weight":30,"indicators":["complejidad","comparación","tiempo"]}]),
 (2,1,"Lab 2 · Aprendizaje supervisado",["supervisado"],[{"name":"Preparación de datos","weight":30,"indicators":["normalización","partición","limpieza"]},{"name":"Modelo y entrenamiento","weight":40,"indicators":["regresión","árbol","entrenamiento","hiperparámetros"]},{"name":"Evaluación","weight":30,"indicators":["accuracy","f1","validación cruzada"]}]),
 (3,1,"Lab 3 · Redes neuronales",["redes"],[{"name":"Arquitectura","weight":40,"indicators":["capas","activación","neuronas"]},{"name":"Entrenamiento","weight":35,"indicators":["backpropagation","épocas","optimizador","pérdida"]},{"name":"Regularización","weight":25,"indicators":["dropout","overfitting"]}]),
 (4,2,"Lab 4 · Procesamiento de lenguaje",["nlp"],[{"name":"Preprocesamiento","weight":35,"indicators":["tokenización","stopwords","lematización"]},{"name":"Representación","weight":35,"indicators":["tf-idf","embeddings"]},{"name":"Clasificación","weight":30,"indicators":["sentimiento","clasificador","f1"]}]),
 (5,2,"Lab 5 · Visión artificial",["vision"],[{"name":"Datos de imágenes","weight":30,"indicators":["aumentación","etiquetas","resolución"]},{"name":"Modelo CNN","weight":40,"indicators":["convolución","pooling","cnn"]},{"name":"Métricas","weight":30,"indicators":["precisión","matriz de confusión"]}]),
 (6,2,"Lab 6 · LLM y RAG",["llm","nlp"],[{"name":"Recuperación","weight":35,"indicators":["embeddings","vectorial","chunks"]},{"name":"Prompting","weight":35,"indicators":["prompt","contexto","json"]},{"name":"Evaluación y alucinaciones","weight":30,"indicators":["alucinación","citas","verificación"]}]),
]

@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    with SessionLocal() as db:
        if db.query(Laboratory).count() == 0:
            for lab_id, cohort, name, topics, rubric in SEED:
                db.add(Laboratory(id=lab_id, cohort=cohort, name=name, topics=topics, rubric_version="1.0", rubric=rubric, description="Descripción y objetivos por completar con la guía oficial del laboratorio."))
            db.commit()
        seed_users(db)
    yield


app = FastAPI(title=APP_NAME, version="1.0.0", description="API para gestión de evidencias, rúbricas y evaluaciones.", lifespan=lifespan)
if CORS_ORIGINS:  # en producción el frontend se sirve desde el mismo dominio: CORS cerrado salvo que se configure
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


app.include_router(auth_router)
app.include_router(router)

frontend = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
