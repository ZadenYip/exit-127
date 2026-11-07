import logging

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from infra.pg.exception import is_unique_constraint_violation
from v1.auth.error.errors import LoginIdAlreadyExistsError, UserNotFoundError
from v1.auth.models import User
from v1.auth.roles import Role

logger = logging.getLogger(__name__)


class UserRepo:
    """PostgreSQL access for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_user(self, *, log_id: str, password_hash: str, role: Role) -> int:
        try:
            async with self._session.begin():
                user = User(
                    login_id=log_id,
                    nickname=log_id,
                    role=role,
                    password_hash=password_hash,
                )
                self._session.add(user)
                await self._session.flush()
                if user.id is None:
                    raise RuntimeError("Database did not return a user ID.")
                user_id = user.id
        except IntegrityError as exc:
            if not is_unique_constraint_violation(exc):
                raise
            raise LoginIdAlreadyExistsError from exc

        logger.info("User registration transaction committed; user_id=%s", user_id)
        return user_id

    async def get_auth_data(self, *, log_id: str) -> tuple[int, str, Role] | None:
        async with self._session.begin():
            row = (await self._session.exec(
                select(User.id, User.password_hash, User.role).where(
                    User.login_id == log_id
                )
            )).one_or_none()
        if row is None:
            return None
        user_id, password_hash, role = row
        if user_id is None:
            raise RuntimeError("Persisted user is missing its ID.")
        return user_id, password_hash, Role(role)

    async def get_user_role(self, *, user_id: int) -> Role:
        logger.info("Loading role for user_id=%s", user_id)
        async with self._session.begin():
            role = (await self._session.exec(
                select(User.role).where(User.id == user_id)
            )).one_or_none()
        if role is None:
            raise UserNotFoundError(f"User {user_id} does not exist.")
        logger.info("Loaded role for user_id=%s", user_id)
        return Role(role)
