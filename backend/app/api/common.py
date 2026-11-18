from app.models.entities import User


def student_scope(user: User) -> int | None:
    """Los estudiantes solo ven lo suyo (filtro por id de usuario); el docente ve todo."""
    return None if user.role == "docente" else user.id
