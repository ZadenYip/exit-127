from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status

from v1.auth.session import StudentUser
from v1.classes.deps import StudentSvcDep
from v1.classes.errors import (
    ClassMembershipRequiredError,
    ClassNotFoundError,
    InviteNotFoundError,
    InvitePassphraseMismatchError,
)
from v1.classes.http_errors import class_not_found
from v1.classes.schemas import JoinClassReq

router = APIRouter(prefix="/classes", tags=["班级"])
_ClassId = Annotated[int, Path(gt=0)]


@router.post(":join", response_model=bool)
async def join_class(
    req: JoinClassReq,
    current_user: StudentUser,
    student_svc: StudentSvcDep,
) -> bool:
    try:
        return await student_svc.join_class(
            invite_code=req.invite_code,
            passphrase=req.passphrase,
            student_id=current_user.user_id,
        )
    except InviteNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "INVITE_NOT_FOUND", "message": "加入链接无效或已过期"},
        ) from exc
    except InvitePassphraseMismatchError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVITE_PASSPHRASE_MISMATCH", "message": "暗号不匹配"},
        ) from exc


@router.post(
    "/{class_id}:leave",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def leave_class(
    class_id: _ClassId,
    current_user: StudentUser,
    student_svc: StudentSvcDep,
) -> None:
    try:
        await student_svc.leave_class(
            class_id=class_id,
            student_id=current_user.user_id,
        )
    except ClassNotFoundError as _:
        raise class_not_found()
    except ClassMembershipRequiredError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "你不是该班级成员"},
        ) from exc
