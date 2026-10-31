import logging
import uuid

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from infra.pg.exception import is_unique_constraint_violation
from infra.pg.pg import PGSessionDep
from v1.auth.bcrypt import hash_password
from v1.auth.models import User
from v1.auth.roles import Role


logger = logging.getLogger(__name__)


class LoginIdAlreadyExistsError(Exception):
    """登录 ID 已经存在。"""


class UserNotFoundError(Exception):
    """用户不存在。"""


class SessionIdCollisionError(Exception):
    """会话 ID 冲突。"""


class UserSession(BaseModel):
    user_id: int
    role: Role


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

SESSION_TTL_SECONDS = 24 * 60 * 60
SESSION_ID_MAX_ATTEMPTS = 3

async def create_login_session(
    *,
    redis: Redis,
    session: PGSessionDep,
    user_id: int,
) -> str:
    logger.info("Creating Redis login session for user_id=%s", user_id)
    role = get_user_role(session=session, user_id=user_id)
    session_data = UserSession(user_id=user_id, role=role).model_dump_json()

    for _ in range(SESSION_ID_MAX_ATTEMPTS):
        session_id = str(uuid.uuid4())
        logger.info("Attempting Redis login-session insert for user_id=%s", user_id)
        try:
            created = await redis.set(
                session_id,
                session_data,
                ex=SESSION_TTL_SECONDS,
                nx=True,
            )
        except RedisError:
            logger.exception(
                "Redis failed to create login session for user_id=%s", user_id
            )
            raise
        if created:
            logger.info("Redis login session created for user_id=%s", user_id)
            return session_id

    raise SessionIdCollisionError(
        f"Could not create a unique session ID after {SESSION_ID_MAX_ATTEMPTS} attempts."
    )
