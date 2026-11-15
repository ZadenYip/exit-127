from fastapi import HTTPException, status


def class_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "CLASS_NOT_FOUND", "message": "班级不存在"},
    )
