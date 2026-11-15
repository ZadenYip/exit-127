from datetime import datetime, timezone
from uuid import UUID

from v1.classes.errors import (
    ClassMembershipRequiredError,
    ClassNotFoundError,
    InviteNotFoundError,
    InvitePassphraseMismatchError,
)
from v1.classes.repo import ClassRepo


class StudentSvc:
    """学生班级服务，处理使用邀请加入班级及退出班级。"""

    def __init__(self, repo: ClassRepo) -> None:
        self._repo = repo

    async def join_class(
        self, *, invite_code: str, passphrase: str | None, student_id: int
    ) -> bool:
        """使用邀请码加入班级，如果学生本身是班级成员会返回 False，如果成功加入班级会返回 True。"""
        try:
            parsed_invite_code = UUID(invite_code)
        except ValueError as exc:
            raise InviteNotFoundError from exc

        async with self._repo.transaction():
            invite_and_class = await self._repo.get_invite_and_class_for_update(
                invite_code=parsed_invite_code
            )
            if invite_and_class is None:
                raise InviteNotFoundError
            invite, class_row = invite_and_class
            if invite.expires_at <= datetime.now(timezone.utc):
                raise InviteNotFoundError
            if invite.passphrase is not None and passphrase != invite.passphrase:
                raise InvitePassphraseMismatchError
            if class_row.id is None:
                raise RuntimeError("Persisted class is missing its ID.")
            return await self._repo.add_member_if_absent(
                class_id=class_row.id, student_id=student_id
            )

    async def leave_class(self, *, class_id: int, student_id: int) -> None:
        async with self._repo.transaction():
            if not await self._repo.is_class_active(class_id=class_id):
                raise ClassNotFoundError
            if not await self._repo.delete_membership(
                class_id=class_id, student_id=student_id
            ):
                raise ClassMembershipRequiredError
