import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from tests.v1.classes.conftest import create_user
from v1.auth.roles import Role
from v1.auth.session import UserSession
from v1.classes.errors import ClassNotFoundError
from v1.classes.repo import ClassRepo
from v1.classes.schemas import ClassCreateReq
from v1.classes.services.common import ClassSvc
from v1.classes.services.teacher import TeacherSvc


@pytest.mark.anyio
async def test_common_service_hides_other_teachers_class(backend: Backend) -> None:
    """验证老师无法查看其他老师的班级详情。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="svc-view-teacher", role=Role.TEACHER
        )
        other_teacher_id = await create_user(
            session, login_id="svc-view-other", role=Role.TEACHER
        )
        teacher_service = TeacherSvc(ClassRepo(session))
        created = await teacher_service.create_class(
            req=ClassCreateReq(name="可见性班"), teacher_id=teacher_id
        )
        common = ClassSvc(ClassRepo(session))
        with pytest.raises(ClassNotFoundError):
            await common.get_class(
                class_id=created.id,
                current_user=UserSession(user_id=other_teacher_id, role=Role.TEACHER),
            )


@pytest.mark.anyio
async def test_common_service_hides_class_from_admin(backend: Backend) -> None:
    """验证管理员角色不能查看班级详情。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="svc-view-teacher", role=Role.TEACHER
        )
        teacher_service = TeacherSvc(ClassRepo(session))
        created = await teacher_service.create_class(
            req=ClassCreateReq(name="可见性班"), teacher_id=teacher_id
        )
        common = ClassSvc(ClassRepo(session))
        with pytest.raises(ClassNotFoundError):
            await common.get_class(
                class_id=created.id,
                current_user=UserSession(user_id=1, role=Role.ADMIN),
            )
