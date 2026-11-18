"""Orquestación de la evaluación con IA: arma el resultado con la rúbrica oficial y calcula la nota."""
from datetime import datetime

from app.models.entities import Laboratory
from app.services.ai_evaluator import evaluar_evidencia_con_ia
from app.services.rubrics import calculate_grade


def level(score: float) -> str:
    return ("Sobresaliente" if score >= 4.5 else "Alto" if score >= 3.5
            else "Básico" if score >= 2.5 else "Bajo" if score > 0 else "Sin evidencia")


def run_ai_evaluation(lab: Laboratory, text: str, evidence_name: str, extracted: bool, model_name: str) -> dict:
    """Devuelve {result, grade, used_model, fallback}. La nota SIEMPRE la calcula el backend."""
    ai = evaluar_evidencia_con_ia(text, lab.rubric, model_name)
    fallback = bool(ai.get("fallback"))
    by_name = {str(c.get("name", "")).strip().casefold(): c for c in ai.get("crit", [])}

    crit, normalized = [], []
    for rubric_item in lab.rubric:
        found = by_name.get(rubric_item["name"].strip().casefold())
        score = max(0.0, min(5.0, float(found["score"]))) if found else 0.0
        justification = found.get("justification") if found else "El modelo no evaluó este criterio."
        crit.append({"criterio": rubric_item["name"], "peso": rubric_item["weight"], "score": score,
                     "nivel": level(score), "evidencia": justification,
                     "fortaleza": None, "brecha": None if found else "Criterio sin evaluar"})
        normalized.append({"score": score, "weight": float(rubric_item["weight"])})

    grade = calculate_grade(normalized)
    used_model = "respaldo-sin-llm" if fallback else model_name
    result = {"laboratorio": lab.name, "version_rubrica": lab.rubric_version, "modelo": used_model,
              "fecha": datetime.utcnow().date().isoformat(), "summary": ai.get("summary"),
              "fallback_reason": ai.get("fallback_reason"),
              "strengths": ai.get("strengths", []), "weaknesses": ai.get("weaknesses", []),
              "verificacion": {"texto_extraido": extracted, "evidencia": evidence_name,
                               "sandbox": "no ejecutado en este prototipo"},
              "crit": crit, "preliminary_grade": grade, "fallback": fallback}
    return {"result": result, "grade": grade, "used_model": used_model, "fallback": fallback}
