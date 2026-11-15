import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from v1.auth.error.errors import LoginIdAlreadyExistsError, UserNotFoundError
from v1.auth.repo import UserRepo
from v1.auth.roles import Role


@pytest.mark.anyio
async def test_create_user_and_load_auth_data(backend: Backend) -> None:
    """应能创建用户并从数据库中加载其认证数据。"""
    async with AsyncSession(backend.engine) as session:
        repo = UserRepo(session)
        user_id = await repo.create_user(
            log_id="student-01",
            password_hash="$2b$12$hash-placeholder",
            role=Role.STUDENT,
        )

        auth_data = await repo.get_auth_data(log_id="student-01")

    assert user_id >= 10000
    assert auth_data == (user_id, "$2b$12$hash-placeholder", Role.STUDENT)


@pytest.mark.anyio
async def test_create_user_maps_duplicate_login_id(backend: Backend) -> None:
    """尝试创建重复登录 ID 的用户时应抛出异常。"""
    async with AsyncSession(backend.engine) as session:
        repo = UserRepo(session)
        await repo.create_user(
            log_id="duplicate-01",
            password_hash="hash",
            role=Role.STUDENT,
        )

        with pytest.raises(LoginIdAlreadyExistsError):
            await repo.create_user(
                log_id="duplicate-01",
                password_hash="another-hash",
                role=Role.TEACHER,
            )


@pytest.mark.anyio
async def test_get_auth_data_returns_none_for_unknown_login_id(backend: Backend) -> None:
    """尝试获取不存在的登录 ID 时应返回 None。"""
    async with AsyncSession(backend.engine) as session:
        auth_data = await UserRepo(session).get_auth_data(log_id="missing-user")

    assert auth_data is None


@pytest.mark.anyio
async def test_get_user_role_returns_role_and_raises_for_unknown_user(backend: Backend) -> None:
    """应能获取用户角色，并在尝试获取不存在的用户时抛出异常。"""
    async with AsyncSession(backend.engine) as session:
        repo = UserRepo(session)
        user_id = await repo.create_user(
            log_id="teacher-01",
            password_hash="hash",
            role=Role.TEACHER,
        )

        role = await repo.get_user_role(user_id=user_id)
        assert role is Role.TEACHER
        with pytest.raises(UserNotFoundError):
            await repo.get_user_role(user_id=user_id + 1000)

