import logging

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from infra.pg.exception import is_unique_constraint_violation
from infra.pg.pg import PGSessionDep
from v1.auth.bcrypt import hash_password
from v1.auth.error.errors import (
    LoginIdAlreadyExistsError,
    UserNotFoundError,
)
from v1.auth.models import User
from v1.auth.roles import Role


logger = logging.getLogger(__name__)


async def register_user(
    *,
    session: PGSessionDep,
    log_id: str,
    password: str,
    role: Role,
) -> int:
    password_hash = await run_in_threadpool(hash_password, password)

    try:
        with session.begin():
            user = User(
                login_id=log_id,
                nickname=log_id,
                role=role,
                password_hash=password_hash,
            )
            session.add(user)
            session.flush()
            logger.info("User record flush completed; user_id=%s", user.id)

            if user.id is None:
                raise RuntimeError("Database did not return a user ID.")
            user_id = user.id
        logger.info("User registration transaction committed; user_id=%s", user_id)
        return user_id
    except IntegrityError as exc:
        if not is_unique_constraint_violation(exc):
            raise
        raise LoginIdAlreadyExistsError from exc


def get_user_role(*, session: Session, user_id: int) -> Role:
    logger.info("Loading role for user_id=%s", user_id)
    with session.begin():
        role = session.exec(
            select(User.role).where(User.id == user_id)
        ).one_or_none()
    if role is None:
        raise UserNotFoundError(f"User {user_id} does not exist.")
    logger.info("Loaded role for user_id=%s", user_id)
    return Role(role)
