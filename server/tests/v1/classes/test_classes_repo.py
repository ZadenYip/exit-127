from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import Backend
from v1.auth.repo import UserRepo
from v1.auth.roles import Role
from v1.classes.repo import ClassRepo


@pytest.mark.anyio
async def test_class_repo_lists_are_scoped_to_user(backend: Backend) -> None:
    """验证多老师、多学生的班级列表隔离，排除未加入及已软删除的班级。"""
    async with AsyncSession(backend.engine) as session:
        teachers = [await create_user(session, login_id=f"scope-t{i}", role=Role.TEACHER) for i in range(2)]
        students = [await create_user(session, login_id=f"scope-s{i}", role=Role.STUDENT) for i in range(3)]
        repo = ClassRepo(session)
        async with repo.transaction():
            first = await repo.add_class(owner_id=teachers[0], name="甲班", description=None)
            second = await repo.add_class(owner_id=teachers[1], name="乙班", description="简介")
            deleted = await repo.add_class(owner_id=teachers[0], name="已删除班", description=None)
            # 学生 0 加入甲班，列表应包含甲班。
            await repo.add_member_if_absent(class_id=first.id, student_id=students[0])
            # 学生 1 加入乙班，验证两个学生不会看到彼此的班级。
            await repo.add_member_if_absent(class_id=second.id, student_id=students[1])
            # 学生 0 也加入待删除班级，验证软删除后该班级不会出现在列表中。
            await repo.add_member_if_absent(class_id=deleted.id, student_id=students[0])
            # 学生 2 不加入任何班级，其列表应为空。
            await repo.soft_delete_owned_class(
                class_id=deleted.id, teacher_id=teachers[0], deleted_at=datetime.now(timezone.utc)
            )
        assert await repo.list_for_teacher(teacher_id=teachers[0]) == [first]
        assert await repo.list_for_teacher(teacher_id=teachers[1]) == [second]
        assert await repo.list_for_student(student_id=students[0]) == [first]
        assert await repo.list_for_student(student_id=students[1]) == [second]
        assert await repo.list_for_student(student_id=students[2]) == []


async def create_user(session: AsyncSession, *, login_id: str, role: Role) -> int:
    return await UserRepo(session).create_user(
        log_id=login_id,
        password_hash="test-hash",
        role=role,
    )


@pytest.mark.anyio
async def test_class_repo_create_list_detail_and_member_count(backend: Backend) -> None:
    """验证创建、列表和详情返回相同四字段数据，并正确查询成员及人数。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="repo-teacher", role=Role.TEACHER
        )
        student_id = await create_user(
            session, login_id="repo-student", role=Role.STUDENT
        )
        repo = ClassRepo(session)
        async with repo.transaction():
            row = await repo.add_class(
                owner_id=teacher_id, name="Repo 班级", description="说明"
            )
            assert row.id is not None
            class_id = row.id
            assert await repo.add_member_if_absent(
                class_id=class_id, student_id=student_id
            )

        teacher_classes = await repo.list_for_teacher(teacher_id=teacher_id)
        student_classes = await repo.list_for_student(student_id=student_id)
        active_class = await repo.get_active_class(class_id=class_id)

        assert [item.id for item in teacher_classes] == [class_id]
        assert [item.id for item in student_classes] == [class_id]
        assert active_class is not None
        assert active_class.model_dump() == {
            "id": class_id,
            "name": "Repo 班级",
            "description": "说明",
            "teacher_id": teacher_id,
        }
        assert active_class == row
        assert await repo.is_member(class_id=class_id, student_id=student_id)
        assert await repo.count_members(class_id=class_id) == 1


@pytest.mark.anyio
async def test_class_repo_duplicate_membership_and_leave(backend: Backend) -> None:
    """验证重复加入不会新增成员，退出后成员关系消失且重复删除返回 False。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="member-teacher", role=Role.TEACHER
        )
        student_id = await create_user(
            session, login_id="member-student", role=Role.STUDENT
        )
        repo = ClassRepo(session)
        async with repo.transaction():
            row = await repo.add_class(
                owner_id=teacher_id, name="成员班", description=None
            )
            class_id = row.id
            assert class_id is not None
            assert await repo.add_member_if_absent(
                class_id=class_id, student_id=student_id
            ) is True
            assert await repo.add_member_if_absent(
                class_id=class_id, student_id=student_id
            ) is False

        async with repo.transaction():
            assert await repo.delete_membership(
                class_id=class_id, student_id=student_id
            )
        assert not await repo.is_member(class_id=class_id, student_id=student_id)
        assert not await repo.delete_membership(
            class_id=class_id, student_id=student_id
        )


@pytest.mark.anyio
async def test_class_repo_soft_delete_and_owned_class_checks(backend: Backend) -> None:
    """验证非所属老师无法锁定或删除班级，软删除后详情及列表隐藏该班级。"""
    async with AsyncSession(backend.engine) as session:
        owner_id = await create_user(
            session, login_id="owner-teacher", role=Role.TEACHER
        )
        other_id = await create_user(
            session, login_id="other-teacher", role=Role.TEACHER
        )
        repo = ClassRepo(session)
        async with repo.transaction():
            row = await repo.add_class(
                owner_id=owner_id, name="软删除班", description=None
            )
            class_id = row.id
        assert class_id is not None

        async with repo.transaction():
            assert not await repo.lock_owned_active_class(
                class_id=class_id, teacher_id=other_id
            )
            assert not await repo.soft_delete_owned_class(
                class_id=class_id,
                teacher_id=other_id,
                deleted_at=datetime.now(timezone.utc),
            )
            assert await repo.soft_delete_owned_class(
                class_id=class_id,
                teacher_id=owner_id,
                deleted_at=datetime.now(timezone.utc),
            )
        assert await repo.get_active_class(class_id=class_id) is None
        assert await repo.list_for_teacher(teacher_id=owner_id) == []


@pytest.mark.anyio
async def test_class_repo_invite_upsert_lookup_and_revoke(backend: Backend) -> None:
    """验证邀请插入、重置和明文暗号更新，以及旧邀请码和撤销后的邀请码失效。"""
    async with AsyncSession(backend.engine) as session:
        teacher_id = await create_user(
            session, login_id="invite-teacher", role=Role.TEACHER
        )
        repo = ClassRepo(session)
        async with repo.transaction():
            row = await repo.add_class(
                owner_id=teacher_id, name="邀请班", description=None
            )
            class_id = row.id
        assert class_id is not None

        first_code = uuid4()
        now = datetime.now(timezone.utc)
        async with repo.transaction():
            assert await repo.lock_owned_active_class(
                class_id=class_id, teacher_id=teacher_id
            )
            await repo.upsert_invite(
                class_id=class_id,
                invite_code=first_code,
                passphrase="first-passphrase",
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        first = await repo.get_invite_and_class_for_update(invite_code=first_code)
        assert first is not None
        assert first[0].passphrase == "first-passphrase"
        await session.commit()

        second_code = uuid4()
        async with repo.transaction():
            await repo.upsert_invite(
                class_id=class_id,
                invite_code=second_code,
                passphrase=None,
                expires_at=now + timedelta(days=7),
                created_at=now,
            )
        assert await repo.get_invite_and_class_for_update(invite_code=first_code) is None
        await session.commit()
        second = await repo.get_invite_and_class_for_update(invite_code=second_code)
        assert second is not None
        assert second[0].passphrase is None
        await session.commit()

        async with repo.transaction():
            assert await repo.delete_invite_for_owned_class(
                class_id=class_id, teacher_id=teacher_id
            )
        assert await repo.get_invite_and_class_for_update(invite_code=second_code) is None
