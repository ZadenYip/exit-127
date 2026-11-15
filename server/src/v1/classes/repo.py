from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, cast
from uuid import UUID

from sqlalchemy import ScalarResult, exists, func, literal, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from v1.classes.models import Class, ClassInvite, ClassMember
from v1.classes.errors import InviteNotFoundError
from v1.classes.schemas import ClassRead


class ClassRepo:
    """班级数据仓储，负责班级、成员和邀请记录的数据库读写。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        async with self._session.begin():
            yield

    async def add_class(
        self, *, owner_id: int, name: str, description: str | None
    ) -> ClassRead:
        result = await self._session.exec(
            pg_insert(Class)
            .values(owner=owner_id, name=name, description=description)
            .returning(
                col(Class.id),
                col(Class.name),
                col(Class.description),
                col(Class.owner).label("teacher_id"),
            )
        )
        return ClassRead.model_validate(result.mappings().one())

    async def list_for_teacher(self, *, teacher_id: int) -> list[ClassRead]:
        result = await self._session.exec(
            select(
                Class.id,
                Class.name,
                Class.description,
                Class.owner,
            ).where(
                Class.owner == teacher_id,
                col(Class.deleted_at).is_(None),
            )
        )
        return [
            ClassRead(
                id=cast(int, class_id),
                name=name,
                description=description,
                teacher_id=owner,
            )
            for class_id, name, description, owner in result.all()
        ]

    async def list_for_student(self, *, student_id: int) -> list[ClassRead]:
        result = await self._session.exec(
            select(
                Class.id,
                Class.name,
                Class.description,
                Class.owner,
            )
            .join(ClassMember, col(ClassMember.class_id) == col(Class.id))
            .where(
                ClassMember.user_id == student_id,
                col(Class.deleted_at).is_(None),
            )
        )
        return [
            ClassRead(
                id=cast(int, class_id),
                name=name,
                description=description,
                teacher_id=owner,
            )
            for class_id, name, description, owner in result.all()
        ]

    async def get_active_class(self, *, class_id: int) -> ClassRead | None:
        result = await self._session.exec(
            select(
                Class.id,
                Class.name,
                Class.description,
                Class.owner,
            ).where(
                Class.id == class_id,
                col(Class.deleted_at).is_(None),
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        row_id, name, description, owner = row
        return ClassRead(
            id=cast(int, row_id),
            name=name,
            description=description,
            teacher_id=owner,
        )

    async def is_member(self, *, class_id: int, student_id: int) -> bool:
        result: ScalarResult[int] = await self._session.exec(
            select(literal(1))
            .select_from(ClassMember)
            .where(
                col(ClassMember.class_id) == class_id,
                col(ClassMember.user_id) == student_id,
            )
            .limit(1)
        )
        return result.first() is not None

    async def count_members(self, *, class_id: int) -> int:
        result = await self._session.exec(
            select(func.count())
            .select_from(ClassMember)
            .where(ClassMember.class_id == class_id)
        )
        return result.one()

    async def soft_delete_owned_class(
        self, *, class_id: int, teacher_id: int, deleted_at: datetime
    ) -> bool:
        result = await self._session.exec(
            update(Class)
            .where(
                col(Class.id) == class_id,
                col(Class.owner) == teacher_id,
                col(Class.deleted_at).is_(None),
            )
            .values(deleted_at=deleted_at)
        )
        return result.rowcount == 1

    async def lock_owned_active_class(
        self, *, class_id: int, teacher_id: int
    ) -> bool:
        """检查班级有效且属于指定老师，并加排他锁。"""
        result = await self._session.exec(
            select(Class)
            .where(
                Class.id == class_id,
                Class.owner == teacher_id,
                col(Class.deleted_at).is_(None),
            )
            .with_for_update()
        )
        return result.one_or_none() is not None

    async def upsert_invite(
        self,
        *,
        class_id: int,
        invite_code: UUID,
        passphrase: str | None,
        expires_at: datetime,
        created_at: datetime,
    ) -> None:
        invite_upsert = pg_insert(ClassInvite).values(
            class_id=class_id,
            invite_code=invite_code,
            passphrase=passphrase,
            expires_at=expires_at,
            created_at=created_at,
        )
        
        await self._session.exec(
            invite_upsert.on_conflict_do_update(
                index_elements=[col(ClassInvite.class_id)],
                set_={
                    "invite_code": invite_code,
                    "passphrase": passphrase,
                    "expires_at": expires_at,
                    "created_at": created_at,
                },
            )
        )
        

    async def delete_invite_for_owned_class(
        self, *, class_id: int, teacher_id: int
    ) -> bool:
        """锁定所属有效班级并删除邀请。

        班级不存在、已删除或归属不符时返回 False；删除成功返回 True。
        班级有效但没有邀请时抛出 InviteNotFoundError，以区分两类不存在。
        """
        class_result = await self._session.exec(
            select(Class)
            .where(
                Class.id == class_id,
                Class.owner == teacher_id,
                col(Class.deleted_at).is_(None),
            )
            .with_for_update()
        )
        if class_result.one_or_none() is None:
            return False

        invite = await self._session.get(ClassInvite, class_id)
        if invite is None:
            raise InviteNotFoundError
        await self._session.delete(invite)
        return True

    async def get_invite_and_class_for_update(
        self, *, invite_code: UUID
    ) -> tuple[ClassInvite, Class] | None:
        result = await self._session.exec(
            select(ClassInvite, Class)
            .join(Class, col(Class.id) == col(ClassInvite.class_id))
            .where(
                ClassInvite.invite_code == invite_code,
                col(Class.deleted_at).is_(None),
            )
            .with_for_update(of=Class)
        )
        return result.one_or_none()

    async def add_member_if_absent(self, *, class_id: int, student_id: int) -> bool:
        membership_insert = pg_insert(ClassMember).values(
            class_id=class_id,
            user_id=student_id,
        )
        result = await self._session.exec(
            membership_insert.on_conflict_do_nothing(
                index_elements=[col(ClassMember.class_id), col(ClassMember.user_id)]
            ).returning(col(ClassMember.class_id))
        )
        return result.scalar_one_or_none() is not None

    async def is_class_active(self, *, class_id: int) -> bool:
        result = await self._session.exec(
            select(
                exists().where(
                    col(Class.id) == class_id,
                    col(Class.deleted_at).is_(None),
                )
            )
        )
        return result.one()

    async def delete_membership(self, *, class_id: int, student_id: int) -> bool:
        membership = await self._session.get(ClassMember, (class_id, student_id))
        if membership is None:
            return False
        await self._session.delete(membership)
        return True
