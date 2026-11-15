from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from v1.auth.repo import UserRepo
from v1.auth.roles import Role
from v1.classes.repo import ClassRepo


async def create_user(session: AsyncSession, *, login_id: str, role: Role) -> int:
    return await UserRepo(session).create_user(
        log_id=login_id,
        password_hash="test-hash",
        role=role,
    )


@dataclass
class ClassContext:
    repo: ClassRepo
    class_id: int
    teacher_id: int
    student_id: int
    other_teacher_id: int


@pytest.fixture
async def class_context(backend: Backend) -> AsyncIterator[ClassContext]:
    """准备所属老师、其他老师、未入班学生及无邀请班级，每个测试独立使用。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(session, login_id="svc-t", role=Role.TEACHER)
        student_id = await create_user(session, login_id="svc-s", role=Role.STUDENT)
        other_teacher_id = await create_user(session, login_id="svc-other", role=Role.TEACHER)
        repo = ClassRepo(session)
        async with repo.transaction():
            created = await repo.add_class(
                owner_id=teacher_id, name="服务班", description=None
            )
        yield ClassContext(repo, created.id, teacher_id, student_id, other_teacher_id)
