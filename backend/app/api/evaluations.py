from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_docente
from app.core.database import get_db
from app.models.entities import Evaluation, Evidence, Laboratory, User
from app.schemas.contracts import ApprovalUpdate, EvaluationCreate
from app.services.ai_evaluator import default_model
from app.services.evaluation_service import run_ai_evaluation
from app.services.evidence_store import read_evidence_bytes
from app.services.evidence_text import extract_text_from_bytes
from app.services.rubrics import calculate_grade, validate_rubric

router = APIRouter(tags=["evaluaciones"])


@router.post("/laboratories/{laboratory_id}/evaluations")
def create_evaluation(laboratory_id: int, payload: EvaluationCreate, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    lab = db.get(Laboratory, laboratory_id)
    if not lab:
        raise HTTPException(404, "Laboratorio no encontrado")
    check = validate_rubric(lab.rubric)
    if not check["valid"]:
        raise HTTPException(422, detail=check)
    if payload.rubric_version != lab.rubric_version:
        raise HTTPException(409, "La versión de rúbrica cambió. Actualiza y vuelve a evaluar.")
    criteria_results = payload.result.get("crit", [])
    if not isinstance(criteria_results, list) or len(criteria_results) != len(lab.rubric):
        raise HTTPException(422, "La cantidad de resultados no coincide con los criterios de la rúbrica oficial")

    normalized = []
    for rubric_item, result_item in zip(lab.rubric, criteria_results):
        if not isinstance(result_item, dict):
            raise HTTPException(422, "Cada resultado de criterio debe ser un objeto")
        name = result_item.get("criterio")
        if name is not None and str(name).strip().casefold() != rubric_item["name"].strip().casefold():
            raise HTTPException(422, "El nombre/orden de los criterios no coincide con la rúbrica vigente")
        try:
            score = float(result_item.get("score"))
        except (TypeError, ValueError):
            raise HTTPException(422, "Cada criterio necesita una puntuación numérica")
        if not 0 <= score <= 5:
            raise HTTPException(422, "Cada puntuación debe estar entre 0 y 5")
        normalized.append({"score": score, "weight": float(rubric_item["weight"])})

    # La nota la calcula siempre el backend con los pesos oficiales; se ignora la que envía el cliente.
    backend_grade = calculate_grade(normalized)
    result_data = dict(payload.result)
    result_data["preliminary_grade"] = backend_grade
    is_student = user.role == "estudiante"  # el estudiante siempre queda como autor; el docente puede indicar el nombre
    record = Evaluation(laboratory_id=laboratory_id,
                        student=user.name if is_student else payload.student.strip() or user.name,
                        student_id=user.id if is_student else None,
                        rubric_version=lab.rubric_version, model_name=payload.model_name,
                        preliminary_grade=backend_grade, result=result_data)
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "preliminary_grade": record.preliminary_grade, "approved": record.approved}


@router.post("/laboratories/{laboratory_id}/evaluations/ai-auto")
def create_ai_automated_evaluation(laboratory_id: int, student_id: int | None = None,
                                   model_name: str | None = None, db: Session = Depends(get_db),
                                   user: User = Depends(get_current_user)):
    """Evalúa con un LLM la última evidencia del estudiante; la nota la calcula el backend."""
    lab = db.get(Laboratory, laboratory_id)
    if not lab:
        raise HTTPException(404, "Laboratorio no encontrado")
    check = validate_rubric(lab.rubric)
    if not check["valid"]:
        raise HTTPException(422, detail={"error": "La rúbrica del laboratorio tiene inconsistencias", "details": check})

    target = user
    if user.role == "docente" and student_id is not None:
        target = db.get(User, student_id)
        if not target:
            raise HTTPException(404, "Estudiante no encontrado")

    evidence = (db.query(Evidence)
                .filter(Evidence.laboratory_id == laboratory_id, Evidence.student_id == target.id)
                .order_by(Evidence.uploaded_at.desc(), Evidence.id.desc()).first())
    if not evidence:
        raise HTTPException(422, "No hay evidencias cargadas para este laboratorio. Sube un archivo primero.")

    data = read_evidence_bytes(evidence)
    if data is None:
        raise HTTPException(422, f"El archivo «{evidence.original_name}» ya no está disponible. Súbelo de nuevo.")
    text, extracted = extract_text_from_bytes(data, evidence.original_name)
    if not extracted:
        raise HTTPException(422, text.strip("[]") + " Formatos admitidos: PDF con texto, .txt, .py, .js, .html.")

    outcome = run_ai_evaluation(lab, text, evidence.original_name, extracted, model_name or default_model())
    record = Evaluation(laboratory_id=laboratory_id, student=target.name, student_id=target.id,
                        rubric_version=lab.rubric_version, model_name=outcome["used_model"],
                        preliminary_grade=outcome["grade"], result=outcome["result"])
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"status": "success", "evaluation_id": record.id, "student": target.name,
            "preliminary_grade": outcome["grade"], "fallback": outcome["fallback"],
            "ai_analysis": outcome["result"]}


@router.patch("/evaluations/{evaluation_id}/approval")
def approve_evaluation(evaluation_id: int, payload: ApprovalUpdate, db: Session = Depends(get_db),
                       docente: User = Depends(require_docente)):
    record = db.get(Evaluation, evaluation_id)
    if not record:
        raise HTTPException(404, "Evaluación no encontrada")
    if payload.approved and payload.final_grade is None:
        raise HTTPException(422, "La aprobación docente requiere especificar una nota final")
    record.approved = payload.approved
    record.final_grade = payload.final_grade if payload.approved else None
    if payload.teacher_feedback is not None:
        record.teacher_feedback = payload.teacher_feedback
    record.approved_by = docente.id if payload.approved else None
    record.approved_at = datetime.utcnow() if payload.approved else None
    db.commit()
    return {"id": record.id, "approved": record.approved, "final_grade": record.final_grade,
            "teacher_feedback": record.teacher_feedback}


@router.get("/evaluations")
def list_evaluations(student: str | None = None, laboratory_id: int | None = None,
                     approved: bool | None = None, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    query = db.query(Evaluation)
    if user.role == "docente":
        if student:
            query = query.filter(Evaluation.student == student)
        if approved is not None:
            query = query.filter(Evaluation.approved == approved)
    else:  # el estudiante solo ve sus evaluaciones ya aprobadas y publicadas
        query = query.filter(Evaluation.student_id == user.id, Evaluation.approved.is_(True))
    if laboratory_id is not None:
        query = query.filter(Evaluation.laboratory_id == laboratory_id)
    return query.order_by(Evaluation.created_at.desc(), Evaluation.id.desc()).all()


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = db.get(Evaluation, evaluation_id)
    if not record or (user.role != "docente" and not (record.student_id == user.id and record.approved)):
        raise HTTPException(404, "Evaluación no encontrada")
    return record
