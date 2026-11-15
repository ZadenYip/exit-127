from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from v1.auth.session import TeacherUser
from v1.classes.deps import TeacherSvcDep
from v1.classes.errors import ClassNotFoundError, InviteNotFoundError
from v1.classes.http_errors import class_not_found
from v1.classes.schemas import ClassCreateReq, ClassRead, JoinLinkRead, JoinLinkReq

router = APIRouter(prefix="/classes", tags=["班级"])
_ClassId = Annotated[int, Path(gt=0)]


@router.post("", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
async def create_class(
    req: ClassCreateReq,
    current_user: TeacherUser,
    teacher_svc: TeacherSvcDep,
) -> ClassRead:
    return await teacher_svc.create_class(req=req, teacher_id=current_user.user_id)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(
    class_id: _ClassId,
    current_user: TeacherUser,
    teacher_svc: TeacherSvcDep,
) -> None:
    try:
        await teacher_svc.delete_class(
            class_id=class_id,
            teacher_id=current_user.user_id,
        )
    except ClassNotFoundError as _:
        raise class_not_found()


@router.post(
    "/{class_id}:createJoinLink",
    response_model=JoinLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_reset_join_link(
    class_id: _ClassId,
    req: JoinLinkReq,
    current_user: TeacherUser,
    teacher_svc: TeacherSvcDep,
) -> JoinLinkRead:
    try:
        return await teacher_svc.create_or_reset_join_link(
            class_id=class_id,
            teacher_id=current_user.user_id,
            passphrase=req.passphrase,
        )
    except ClassNotFoundError as _:
        raise class_not_found()


@router.post(
    "/{class_id}:revokeJoinLink",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_join_link(
    class_id: _ClassId,
    current_user: TeacherUser,
    teacher_svc: TeacherSvcDep,
) -> None:
    try:
        revoked = await teacher_svc.revoke_join_link(
            class_id=class_id,
            teacher_id=current_user.user_id,
        )
    except InviteNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"code": "INVITE_NOT_FOUND", "message": "邀请已不存在"},
        )
    if not revoked:
        raise class_not_found()
