import logging
import uuid

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from v1.auth.bcrypt import hash_password, verify_password
from v1.auth.error.errors import SessionIdCollisionError
from v1.auth.repo import UserRepo
from v1.auth.roles import Role
from v1.auth.session import SESSION_TTL_SECONDS, UserSession

logger = logging.getLogger(__name__)
SESSION_ID_MAX_ATTEMPTS = 3


class UserService:
    """Coordinates user persistence, password checks, and Redis sessions."""

    def __init__(self, *, repo: UserRepo, redis: Redis) -> None:
        self._repo = repo
        self._redis = redis

    async def register(
        self, *, log_id: str, password: str, role: Role
    ) -> tuple[int, str]:
        password_hash = await run_in_threadpool(hash_password, password)
        user_id = await self._repo.create_user(
            log_id=log_id,
            password_hash=password_hash,
            role=role,
        )
        session_id = await self.create_login_session(user_id=user_id, role=role)
        return user_id, session_id

    async def authenticate(self, *, log_id: str, password: str) -> UserSession | None:
        auth_data = await self._repo.get_auth_data(log_id=log_id)
        if auth_data is None:
            return None
        user_id, password_hash, role = auth_data
        password_matches = await run_in_threadpool(
            verify_password, password, password_hash
        )
        if not password_matches:
            return None
        return UserSession(user_id=user_id, role=role)

    async def create_login_session(self, *, user_id: int, role: Role) -> str:
        logger.info("Creating Redis login session for user_id=%s", user_id)
        session_data = UserSession(user_id=user_id, role=role).model_dump_json()
        for _ in range(SESSION_ID_MAX_ATTEMPTS):
            session_id = str(uuid.uuid4())
            try:
                created = await self._redis.set(
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
