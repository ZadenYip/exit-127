import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from tests.v1.classes.conftest import ClassContext, create_user
from v1.auth.roles import Role
from v1.classes.errors import ClassNotFoundError, InviteNotFoundError
from v1.classes.repo import ClassRepo
from v1.classes.schemas import ClassCreateReq
from v1.classes.services.student import StudentSvc
from v1.classes.services.teacher import TeacherSvc


@pytest.mark.anyio
async def test_create_invite_for_missing_class(class_context: ClassContext) -> None:
    """验证给不存在的班级创建邀请抛出班级不存在异常。"""
    ctx = class_context
    with pytest.raises(ClassNotFoundError):
        await TeacherSvc(ctx.repo).create_or_reset_join_link(
            class_id=ctx.class_id + 1, teacher_id=ctx.teacher_id, passphrase=None
        )


@pytest.mark.anyio
async def test_create_invite_for_deleted_class(class_context: ClassContext) -> None:
    """验证已删除班级不能创建邀请。"""
    ctx = class_context
    teacher = TeacherSvc(ctx.repo)
    await teacher.delete_class(class_id=ctx.class_id, teacher_id=ctx.teacher_id)
    with pytest.raises(ClassNotFoundError):
        await teacher.create_or_reset_join_link(
            class_id=ctx.class_id, teacher_id=ctx.teacher_id, passphrase=None
        )


@pytest.mark.anyio
async def test_create_invite_for_other_teacher_class(class_context: ClassContext) -> None:
    """验证非所属老师不能创建邀请。"""
    ctx = class_context
    with pytest.raises(ClassNotFoundError):
        await TeacherSvc(ctx.repo).create_or_reset_join_link(
            class_id=ctx.class_id, teacher_id=ctx.other_teacher_id, passphrase=None
        )


@pytest.mark.anyio
async def test_delete_missing_class(class_context: ClassContext) -> None:
    """验证删除不存在的班级抛出班级不存在异常。"""
    ctx = class_context
    with pytest.raises(ClassNotFoundError):
        await TeacherSvc(ctx.repo).delete_class(
            class_id=ctx.class_id + 1, teacher_id=ctx.teacher_id
        )


@pytest.mark.anyio
async def test_delete_other_teacher_class(class_context: ClassContext) -> None:
    """验证非所属老师删除失败且班级仍然有效。"""
    ctx = class_context
    with pytest.raises(ClassNotFoundError):
        await TeacherSvc(ctx.repo).delete_class(
            class_id=ctx.class_id, teacher_id=ctx.other_teacher_id
        )
    assert await ctx.repo.is_class_active(class_id=ctx.class_id)


@pytest.mark.anyio
async def test_revoke_invalidates_invite(class_context: ClassContext) -> None:
    """验证撤销成功返回 True，且原邀请不能再加入班级。"""
    ctx = class_context
    teacher = TeacherSvc(ctx.repo)
    invite = await teacher.create_or_reset_join_link(
        class_id=ctx.class_id, teacher_id=ctx.teacher_id, passphrase=None
    )
    assert await teacher.revoke_join_link(class_id=ctx.class_id, teacher_id=ctx.teacher_id) is True
    with pytest.raises(InviteNotFoundError):
        await StudentSvc(ctx.repo).join_class(
            invite_code=str(invite.invite_code), passphrase=None, student_id=ctx.student_id
        )


@pytest.mark.anyio
async def test_revoke_absent_invite(class_context: ClassContext) -> None:
    """验证有效班级没有邀请时撤销抛出邀请不存在异常。"""
    ctx = class_context
    with pytest.raises(InviteNotFoundError):
        await TeacherSvc(ctx.repo).revoke_join_link(
            class_id=ctx.class_id, teacher_id=ctx.teacher_id
        )


@pytest.mark.anyio
async def test_teacher_service_reset_invalidates_old_invite(backend: Backend) -> None:
    """验证重置生成新的邀请码，并使旧邀请码无法加入班级。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="svc-invite-t", role=Role.TEACHER
        )
        teacher = TeacherSvc(ClassRepo(session))
        created = await teacher.create_class(
            req=ClassCreateReq(name="邀请服务班"), teacher_id=teacher_id
        )
        first = await teacher.create_or_reset_join_link(
            class_id=created.id, teacher_id=teacher_id, passphrase="secret"
        )
        second = await teacher.create_or_reset_join_link(
            class_id=created.id, teacher_id=teacher_id, passphrase=None
        )
        assert first.invite_code != second.invite_code
        with pytest.raises(InviteNotFoundError):
            await StudentSvc(ClassRepo(session)).join_class(
                invite_code=str(first.invite_code),
                passphrase="secret",
                student_id=99999,
            )


@pytest.mark.anyio
async def test_teacher_service_failed_reset_rolls_back(
    backend: Backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证重置邀请写入后发生异常时事务回滚，原邀请码和暗号仍有效。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(session, login_id="rollback-t", role=Role.TEACHER)
        repo = ClassRepo(session)
        teacher = TeacherSvc(repo)
        created = await teacher.create_class(req=ClassCreateReq(name="回滚班"), teacher_id=teacher_id)
        original = await teacher.create_or_reset_join_link(
            class_id=created.id, teacher_id=teacher_id, passphrase="original"
        )
        upsert = repo.upsert_invite

        async def fail_after_write(**kwargs):
            await upsert(**kwargs)
            raise RuntimeError("simulated failure after write")

        monkeypatch.setattr(repo, "upsert_invite", fail_after_write)
        with pytest.raises(RuntimeError, match="simulated failure after write"):
            await teacher.create_or_reset_join_link(
                class_id=created.id, teacher_id=teacher_id, passphrase="changed"
            )

    async with AsyncSession(backend.engine) as verification_session:
        saved = await ClassRepo(verification_session).get_invite_and_class_for_update(
            invite_code=original.invite_code
        )
        assert saved is not None
        assert saved[0].passphrase == "original"


@pytest.mark.anyio
async def test_teacher_service_soft_delete_invalidates_invite(backend: Backend) -> None:
    """验证软删除班级后原邀请码无法再用于加入。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="svc-delete-t", role=Role.TEACHER
        )
        teacher = TeacherSvc(ClassRepo(session))
        created = await teacher.create_class(
            req=ClassCreateReq(name="待删除服务班"), teacher_id=teacher_id
        )
        invite = await teacher.create_or_reset_join_link(
            class_id=created.id, teacher_id=teacher_id, passphrase=None
        )

        await teacher.delete_class(class_id=created.id, teacher_id=teacher_id)
        with pytest.raises(InviteNotFoundError):
            await StudentSvc(ClassRepo(session)).join_class(
                invite_code=str(invite.invite_code),
                passphrase=None,
                student_id=10001,
            )
