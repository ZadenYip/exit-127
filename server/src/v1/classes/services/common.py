from v1.auth.roles import Role
from v1.auth.session import UserSession
from v1.classes.errors import ClassAccessDeniedError, ClassNotFoundError
from v1.classes.repo import ClassRepo
from v1.classes.schemas import ClassDetail, ClassRead


class ClassSvc:
    """班级共用服务，处理列表、详情及角色对应的访问规则。"""

    def __init__(self, repo: ClassRepo) -> None:
        self._repo = repo

    async def list_classes(self, *, cur_user: UserSession) -> list[ClassRead]:
        if cur_user.role == Role.TEACHER:
            return await self._repo.list_for_teacher(teacher_id=cur_user.user_id)
        if cur_user.role == Role.STUDENT:
            return await self._repo.list_for_student(student_id=cur_user.user_id)
        raise ClassAccessDeniedError

    async def get_class(
        self, *, class_id: int, current_user: UserSession
    ) -> ClassDetail:
        class_row = await self._repo.get_active_class(class_id=class_id)
        if class_row is None:
            raise ClassNotFoundError

        if current_user.role == Role.TEACHER:
            allowed = class_row.teacher_id == current_user.user_id
        elif current_user.role == Role.STUDENT:
            allowed = await self._repo.is_member(
                class_id=class_id, student_id=current_user.user_id
            )
        else:
            allowed = False
        if not allowed:
            raise ClassNotFoundError

        return ClassDetail(
            **class_row.model_dump(),
            member_count=await self._repo.count_members(class_id=class_id),
        )
