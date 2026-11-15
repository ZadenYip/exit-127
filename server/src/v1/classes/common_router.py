from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from v1.auth.session import CurrentUser
from v1.classes.deps import ClassSvcDep
from v1.classes.errors import ClassAccessDeniedError, ClassNotFoundError
from v1.classes.http_errors import class_not_found
from v1.classes.schemas import ClassDetail, ClassRead

router = APIRouter(prefix="/classes", tags=["班级"])
_ClassId = Annotated[int, Path(gt=0)]


@router.get("", response_model=list[ClassRead])
async def list_classes(
    current_user: CurrentUser,
    class_svc: ClassSvcDep,
) -> list[ClassRead]:
    try:
        return await class_svc.list_classes(cur_user=current_user)
    except ClassAccessDeniedError:
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "无权访问班级"},
        )


@router.get("/{class_id}", response_model=ClassDetail)
async def get_class(
    class_id: _ClassId,
    current_user: CurrentUser,
    class_svc: ClassSvcDep,
) -> ClassDetail:
    try:
        return await class_svc.get_class(class_id=class_id, current_user=current_user)
    except ClassNotFoundError:
        raise class_not_found()
