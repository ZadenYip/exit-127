from typing import Annotated

from fastapi import Depends

from infra.pg.pg import PGSessionDep
from infra.redis import RedisDep
from v1.auth.repo import UserRepo
from v1.auth.service import UserService


def get_user_service(session: PGSessionDep, redis: RedisDep) -> UserService:
    return UserService(repo=UserRepo(session), redis=redis)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
