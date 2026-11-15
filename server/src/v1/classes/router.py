from fastapi import APIRouter

from v1.classes import common_router, student_router, teacher_router

router = APIRouter()
router.include_router(common_router.router)
router.include_router(teacher_router.router)
router.include_router(student_router.router)
