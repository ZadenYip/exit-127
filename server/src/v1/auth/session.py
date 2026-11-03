import logging
import uuid

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from v1.auth.error.errors import SessionIdCollisionError
from v1.auth.roles import Role


logger = logging.getLogger(__name__)


class UserSession(BaseModel):
    user_id: int
    role: Role


SESSION_TTL_SECONDS = 24 * 60 * 60
SESSION_ID_MAX_ATTEMPTS = 3

async def create_login_session(
    *,
    redis: Redis,
    user_id: int,
    role: Role,
) -> str:
    logger.info("Creating Redis login session for user_id=%s", user_id)
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