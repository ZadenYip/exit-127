
from sqlalchemy.exc import IntegrityError


def is_unique_constraint_violation(
    err: IntegrityError,
) -> bool:
    """
    是否违反了唯一性约束。
    """
    original = err.orig
    sqlstate = getattr(original, "sqlstate", None)
    return sqlstate == "23505"
