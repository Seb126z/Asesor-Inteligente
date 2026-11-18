from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_docente
from app.core.database import get_db
from app.models.entities import Laboratory, User
from app.schemas.contracts import RubricUpdate
from app.services.rubrics import validate_rubric

router = APIRouter(tags=["laboratorios"])


@router.get("/laboratories")
def list_laboratories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Laboratory).order_by(Laboratory.cohort, Laboratory.id).all()


@router.get("/laboratories/{laboratory_id}")
def get_laboratory(laboratory_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    item = db.get(Laboratory, laboratory_id)
    if not item:
        raise HTTPException(404, "Laboratorio no encontrado")
    return item


@router.put("/laboratories/{laboratory_id}/rubric")
def update_rubric(laboratory_id: int, payload: RubricUpdate, db: Session = Depends(get_db),
                  _: User = Depends(require_docente)):
    item = db.get(Laboratory, laboratory_id)
    if not item:
        raise HTTPException(404, "Laboratorio no encontrado")
    criteria = [criterion.model_dump() for criterion in payload.criteria]
    validation = validate_rubric(criteria)
    if not validation["valid"]:
        raise HTTPException(422, detail=validation)
    item.rubric = criteria
    item.rubric_version = payload.version
    db.commit()
    return {"laboratory_id": item.id, "version": item.rubric_version, **validation}
