import logging
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from redis.exceptions import RedisError

from infra.redis import RedisDep
from v1.auth.roles import Role


logger = logging.getLogger(__name__)


class UserSession(BaseModel):
    user_id: int
    role: Role


SESSION_COOKIE_NAME = "__Host-session_id"
SESSION_TTL_SECONDS = 24 * 60 * 60


async def get_current_user(
    redis: RedisDep,
    session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> UserSession:
    """Resolve the current user from the Redis-backed login session."""
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "请先登录"},
        )

    try:
        session_data = await redis.get(session_id)
    except RedisError:
        logger.exception("Redis failed to load login session")
        raise

    if session_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "登录会话已失效"},
        )

    try:
        return UserSession.model_validate_json(session_data)
    except ValidationError as exc:
        logger.warning("Invalid login session payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "登录会话无效"},
        ) from exc


CurrentUser = Annotated[UserSession, Depends(get_current_user)]


async def require_teacher(cur_user: CurrentUser) -> UserSession:
    if cur_user.role != Role.TEACHER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "仅教师可执行此操作"},
        )
    return cur_user


async def require_student(cur_user: CurrentUser) -> UserSession:
    if cur_user.role != Role.STUDENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "仅学生可执行此操作"},
        )
    return cur_user


TeacherUser = Annotated[UserSession, Depends(require_teacher)]
StudentUser = Annotated[UserSession, Depends(require_student)]
