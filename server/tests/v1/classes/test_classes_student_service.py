from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from tests.v1.classes.conftest import ClassContext, create_user
from v1.auth.roles import Role
from v1.classes.errors import (
    ClassMembershipRequiredError,
    ClassNotFoundError,
    InviteNotFoundError,
    InvitePassphraseMismatchError,
)
from v1.classes.repo import ClassRepo
from v1.classes.schemas import ClassCreateReq
from v1.classes.services.student import StudentSvc
from v1.classes.services.teacher import TeacherSvc
from v1.classes.services import student as student_module


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """固定当前时间，使到期边界测试不受实际运行时刻影响。"""
    fixed_now = datetime(2030, 1, 1, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(student_module, "datetime", FrozenDateTime)
    return fixed_now


@pytest.mark.anyio
async def test_join_with_correct_passphrase(class_context: ClassContext) -> None:
    """验证正确暗号加入返回 True 并保存成员关系。"""
    ctx = class_context
    invite = await TeacherSvc(ctx.repo).create_or_reset_join_link(
        class_id=ctx.class_id, teacher_id=ctx.teacher_id, passphrase="secret"
    )
    assert await StudentSvc(ctx.repo).join_class(
        invite_code=str(invite.invite_code), passphrase="secret", student_id=ctx.student_id
    ) is True
    assert await ctx.repo.is_member(class_id=ctx.class_id, student_id=ctx.student_id)


@pytest.mark.anyio
async def test_join_without_required_passphrase(class_context: ClassContext) -> None:
    """验证省略必需暗号时拒绝加入且不产生成员关系。"""
    ctx = class_context
    invite = await TeacherSvc(ctx.repo).create_or_reset_join_link(
        class_id=ctx.class_id, teacher_id=ctx.teacher_id, passphrase="secret"
    )
    with pytest.raises(InvitePassphraseMismatchError):
        await StudentSvc(ctx.repo).join_class(
            invite_code=str(invite.invite_code), passphrase=None, student_id=ctx.student_id
        )
    assert not await ctx.repo.is_member(class_id=ctx.class_id, student_id=ctx.student_id)


@pytest.mark.anyio
async def test_repeated_join_returns_false(class_context: ClassContext) -> None:
    """验证已有成员重复加入返回 False 且不会增加成员人数。"""
    ctx = class_context
    invite = await TeacherSvc(ctx.repo).create_or_reset_join_link(
        class_id=ctx.class_id, teacher_id=ctx.teacher_id, passphrase=None
    )
    async with ctx.repo.transaction():
        await ctx.repo.add_member_if_absent(class_id=ctx.class_id, student_id=ctx.student_id)
    assert await StudentSvc(ctx.repo).join_class(
        invite_code=str(invite.invite_code), passphrase=None, student_id=ctx.student_id
    ) is False
    assert await ctx.repo.count_members(class_id=ctx.class_id) == 1


@pytest.mark.anyio
async def test_join_unknown_invite(class_context: ClassContext) -> None:
    """验证格式有效但不存在的邀请码不能加入班级。"""
    ctx = class_context
    with pytest.raises(InviteNotFoundError):
        await StudentSvc(ctx.repo).join_class(
            invite_code=str(uuid4()), passphrase=None, student_id=ctx.student_id
        )


@pytest.mark.anyio
async def test_leave_removes_membership(class_context: ClassContext) -> None:
    """验证成员退出后成员关系被删除。"""
    ctx = class_context
    async with ctx.repo.transaction():
        await ctx.repo.add_member_if_absent(class_id=ctx.class_id, student_id=ctx.student_id)
    await StudentSvc(ctx.repo).leave_class(class_id=ctx.class_id, student_id=ctx.student_id)
    assert not await ctx.repo.is_member(class_id=ctx.class_id, student_id=ctx.student_id)


@pytest.mark.anyio
async def test_leave_as_non_member(class_context: ClassContext) -> None:
    """验证非成员退出有效班级抛出需要成员身份的异常。"""
    ctx = class_context
    with pytest.raises(ClassMembershipRequiredError):
        await StudentSvc(ctx.repo).leave_class(class_id=ctx.class_id, student_id=ctx.student_id)


@pytest.mark.anyio
async def test_leave_missing_class(class_context: ClassContext) -> None:
    """验证退出不存在的班级抛出班级不存在异常。"""
    ctx = class_context
    with pytest.raises(ClassNotFoundError):
        await StudentSvc(ctx.repo).leave_class(
            class_id=ctx.class_id + 1, student_id=ctx.student_id
        )


@pytest.mark.anyio
async def test_leave_deleted_class(class_context: ClassContext) -> None:
    """验证班级删除后成员退出抛出班级不存在异常。"""
    ctx = class_context
    async with ctx.repo.transaction():
        await ctx.repo.add_member_if_absent(class_id=ctx.class_id, student_id=ctx.student_id)
    await TeacherSvc(ctx.repo).delete_class(class_id=ctx.class_id, teacher_id=ctx.teacher_id)
    with pytest.raises(ClassNotFoundError):
        await StudentSvc(ctx.repo).leave_class(class_id=ctx.class_id, student_id=ctx.student_id)


@pytest.mark.anyio
async def test_student_service_rejects_wrong_passphrase(backend: Backend) -> None:
    """验证错误暗号抛出暗号不匹配异常，且不新增成员。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="svc-pass-teacher", role=Role.TEACHER
        )
        student_id = await create_user(
            session, login_id="svc-pass-student", role=Role.STUDENT
        )
        teacher = TeacherSvc(ClassRepo(session))
        created = await teacher.create_class(
            req=ClassCreateReq(name="暗号服务班"), teacher_id=teacher_id
        )
        invite = await teacher.create_or_reset_join_link(
            class_id=created.id, teacher_id=teacher_id, passphrase="correct"
        )
        student = StudentSvc(ClassRepo(session))
        with pytest.raises(InvitePassphraseMismatchError):
            await student.join_class(
                invite_code=str(invite.invite_code),
                passphrase="bad",
                student_id=student_id,
            )
        assert not await ClassRepo(session).is_member(
            class_id=created.id, student_id=student_id
        )


@pytest.mark.anyio
async def test_student_service_rejects_invalid_invite_code(backend: Backend) -> None:
    """验证非 UUID 邀请码抛出邀请不存在异常。"""
    async with AsyncSession(backend.engine) as session:
        student = StudentSvc(ClassRepo(session))
        with pytest.raises(InviteNotFoundError):
            await student.join_class(
                invite_code="invalid-uuid", passphrase=None, student_id=99999
            )


@pytest.mark.anyio
async def test_student_service_accepts_unexpired_invite(backend: Backend, fixed_now: datetime) -> None:
    """验证邀请到期前 1 毫秒仍可加入并创建成员关系。

    fixed_now fixture 同时将 StudentSvc 使用的 datetime.now() 固定为该时间，
    避免测试执行期间时间推进导致邀请过期；测试结束后自动恢复。
    """
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(session, login_id="expiry-t", role=Role.TEACHER)
        student_id = await create_user(session, login_id="expiry-s", role=Role.STUDENT)
        repo = ClassRepo(session)
        code = uuid4()
        async with repo.transaction():
            created = await repo.add_class(owner_id=teacher_id, name="到期班", description=None)
            await repo.upsert_invite(
                class_id=created.id, invite_code=code, passphrase=None,
                created_at=fixed_now - timedelta(days=7),
                expires_at=fixed_now + timedelta(milliseconds=1),
            )
        student = StudentSvc(repo)
        assert await student.join_class(
            invite_code=str(code), passphrase=None, student_id=student_id
        ) is True
        assert await repo.is_member(class_id=created.id, student_id=student_id)


@pytest.mark.anyio
async def test_student_service_rejects_invite_at_expiry(backend: Backend, fixed_now: datetime) -> None:
    """验证邀请到期瞬间拒绝加入且不新增成员。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(session, login_id="expiry-t", role=Role.TEACHER)
        student_id = await create_user(session, login_id="expiry-s", role=Role.STUDENT)
        repo = ClassRepo(session)
        code = uuid4()
        async with repo.transaction():
            created = await repo.add_class(owner_id=teacher_id, name="到期班", description=None)
            await repo.upsert_invite(
                class_id=created.id, invite_code=code, passphrase=None,
                created_at=fixed_now - timedelta(days=7),
                expires_at=fixed_now,
            )
        student = StudentSvc(repo)
        with pytest.raises(InviteNotFoundError):
            await student.join_class(
                invite_code=str(code), passphrase=None, student_id=student_id
            )
        assert not await repo.is_member(class_id=created.id, student_id=student_id)


@pytest.mark.anyio
async def test_student_service_rejects_expired_invite(backend: Backend, fixed_now: datetime) -> None:
    """验证邀请过期后拒绝加入且不新增成员。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(session, login_id="expiry-t", role=Role.TEACHER)
        student_id = await create_user(session, login_id="expiry-s", role=Role.STUDENT)
        repo = ClassRepo(session)
        code = uuid4()
        async with repo.transaction():
            created = await repo.add_class(owner_id=teacher_id, name="到期班", description=None)
            await repo.upsert_invite(
                class_id=created.id, invite_code=code, passphrase=None,
                created_at=fixed_now - timedelta(days=7),
                expires_at=fixed_now + timedelta(milliseconds=-1),
            )
        student = StudentSvc(repo)
        with pytest.raises(InviteNotFoundError):
            await student.join_class(
                invite_code=str(code), passphrase=None, student_id=student_id
            )
        assert not await repo.is_member(class_id=created.id, student_id=student_id)
