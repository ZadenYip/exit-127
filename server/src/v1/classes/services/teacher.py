from datetime import datetime, timedelta, timezone
from uuid import uuid7

from v1.classes.errors import ClassNotFoundError
from v1.classes.repo import ClassRepo
from v1.classes.schemas import ClassCreateReq, ClassRead, JoinLinkRead

INVITE_LIFETIME = timedelta(days=7)

class TeacherSvc:
    """教师班级服务，处理创建、删除班级及加入邀请管理。"""

    def __init__(self, repo: ClassRepo) -> None:
        self._repo = repo

    async def create_class(
        self, *, req: ClassCreateReq, teacher_id: int
    ) -> ClassRead:
        async with self._repo.transaction():
            return await self._repo.add_class(
                owner_id=teacher_id, name=req.name, description=req.description
            )

    async def delete_class(self, *, class_id: int, teacher_id: int) -> None:
        async with self._repo.transaction():
            deleted = await self._repo.soft_delete_owned_class(
                class_id=class_id,
                teacher_id=teacher_id,
                deleted_at=datetime.now(timezone.utc),
            )
            if not deleted:
                raise ClassNotFoundError

    async def create_or_reset_join_link(
        self, *, class_id: int, teacher_id: int, passphrase: str | None
    ) -> JoinLinkRead:
        invite_code = uuid7()
        now = datetime.now(timezone.utc)
        async with self._repo.transaction():
            if not await self._repo.lock_owned_active_class(
                class_id=class_id, teacher_id=teacher_id
            ):
                raise ClassNotFoundError
            await self._repo.upsert_invite(
                class_id=class_id,
                invite_code=invite_code,
                passphrase=passphrase,
                expires_at=now + INVITE_LIFETIME,
                created_at=now,
            )
        return JoinLinkRead(invite_code=invite_code)

    async def revoke_join_link(self, *, class_id: int, teacher_id: int) -> bool:
        async with self._repo.transaction():
            return await self._repo.delete_invite_for_owned_class(
                class_id=class_id, teacher_id=teacher_id
            )
