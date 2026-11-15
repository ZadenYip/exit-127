import json

import pytest
from fastapi import HTTPException
from redis.exceptions import ResponseError

from tests.conftest import Backend
from v1.auth.roles import Role
from v1.auth.session import (
    SESSION_COOKIE_NAME,
    UserSession,
    get_current_user,
    require_student,
    require_teacher,
)


@pytest.mark.anyio
async def test_get_current_user_rejects_missing_cookie(backend: Backend) -> None:
    """没有会话 Cookie 时应拒绝请求。"""
    with pytest.raises(HTTPException) as error:
        await get_current_user(backend.redis, None)

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_rejects_expired_session(backend: Backend) -> None:
    """Redis 中不存在会话时应返回未认证。"""
    with pytest.raises(HTTPException) as error:
        await get_current_user(backend.redis, "expired-session")

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_decodes_session(backend: Backend) -> None:
    """应能从 Redis 会话数据中还原当前用户。"""
    session = UserSession(user_id=123, role=Role.TEACHER)
    await backend.redis.set("active-session", session.model_dump_json())

    user = await get_current_user(backend.redis, "active-session")

    assert user == session


@pytest.mark.anyio
@pytest.mark.parametrize("payload", ["not-json", json.dumps({"user_id": "bad", "role": 1}), '{"user_id": 1, "role": 99}'])
async def test_get_current_user_rejects_invalid_session_payload(
    payload: str, backend: Backend
) -> None:
    """会话内容不是合法用户数据时应拒绝请求。"""
    await backend.redis.set("invalid-session", payload)
    with pytest.raises(HTTPException) as error:
        await get_current_user(backend.redis, "invalid-session")

    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_get_current_user_propagates_redis_errors(backend: Backend) -> None:
    """读取 Redis 会话失败时应继续抛出 Redis 错误。"""
    await backend.redis.hset("active-session", mapping={"invalid": "value"})

    with pytest.raises(ResponseError, match="WRONGTYPE"):
        await get_current_user(backend.redis, "active-session")


@pytest.mark.anyio
async def test_role_requirements_accept_only_the_matching_role() -> None:
    """教师和学生权限依赖只能通过对应角色。"""
    teacher = UserSession(user_id=10, role=Role.TEACHER)
    student = UserSession(user_id=11, role=Role.STUDENT)

    assert await require_teacher(teacher) is teacher
    assert await require_student(student) is student

    with pytest.raises(HTTPException) as teacher_error:
        await require_teacher(student)
    with pytest.raises(HTTPException) as student_error:
        await require_student(teacher)

    assert teacher_error.value.status_code == 403
    assert student_error.value.status_code == 403


def test_session_cookie_name_is_host_scoped() -> None:
    """会话 Cookie 应使用 Host 前缀名称。"""
    assert SESSION_COOKIE_NAME == "__Host-session_id"
