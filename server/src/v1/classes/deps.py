from typing import Annotated

from fastapi import Depends

from infra.pg.pg import PGSessionDep
from v1.classes.repo import ClassRepo
from v1.classes.services import ClassSvc, StudentSvc, TeacherSvc


def get_class_svc(session: PGSessionDep) -> ClassSvc:
    return ClassSvc(ClassRepo(session))


def get_teacher_svc(session: PGSessionDep) -> TeacherSvc:
    return TeacherSvc(ClassRepo(session))


def get_student_svc(session: PGSessionDep) -> StudentSvc:
    return StudentSvc(ClassRepo(session))


ClassSvcDep = Annotated[ClassSvc, Depends(get_class_svc)]
TeacherSvcDep = Annotated[TeacherSvc, Depends(get_teacher_svc)]
StudentSvcDep = Annotated[StudentSvc, Depends(get_student_svc)]
