from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from langchain_protocol import ErrorResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from infra.pg.pg import PGSessionDep
from infra.redis import RedisDep
from v1.auth.error.errors import LoginIdAlreadyExistsError
from v1.auth.login import authenticate_user
from v1.auth.register import register_user
from v1.auth.roles import Role
from v1.auth.session import SESSION_TTL_SECONDS, create_login_session


router = APIRouter(prefix="/auth", tags=["身份认证"])
SESSION_COOKIE_NAME = "__Host-session_id"

_LoginId = Annotated[str, Field(min_length=3, max_length=16)]
_Password = Annotated[str, Field(min_length=8, max_length=16)]


class RegisterReq(BaseModel):
    log_id: _LoginId
    password: _Password
    role: Literal[Role.STUDENT, Role.TEACHER]


@router.post(
    "/register",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "注册成功",
            "headers": {
                "Set-Cookie": {
                    "description": "登录会话 Cookie",
                    "schema": {"type": "string"},
                }
            },
        },
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "登录 ID 已存在",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "LOGIN_ID_ALREADY_EXISTS",
                            "message": "登录 ID 已存在",
                        }
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ErrorResponse,
            "description": "无法创建唯一的会话 ID",
            "content": {
                "application/json": {
                    "example": {
                        "detail": {
                            "code": "SESSION_ID_COLLISION",
                            "message": "无法创建登录会话",
                        }
                    }
                }
            },
        },
    },
)
async def register(
    req: RegisterReq,
    response: Response,
    request: Request,
    session: PGSessionDep,
    redis: RedisDep,
):
    try:
        user_id = await register_user(
            session=session,
            log_id=req.log_id,
            password=req.password,
            role=req.role)
    except LoginIdAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LOGIN_ID_ALREADY_EXISTS",
                "message": "登录 ID 已存在",
            },
        ) from exc

    request.state.user_id = user_id

    session_id = await create_login_session(
        redis=redis,
        user_id=user_id,
        role=req.role,
    )
    
    # 设置登录会话 Cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )

    return {"message": "注册成功", "id": user_id}

class LoginReq(BaseModel):
    log_id: _LoginId
    password: _Password


@router.post("/login", responses={
    401: {"description": "登录 ID 或密码错误"},
    500: {"model": ErrorResponse, "description": "无法创建登录会话"},
})
async def login(
    req: LoginReq,
    response: Response,
    request: Request,
    session: PGSessionDep,
    redis: RedisDep,
):
    user = await run_in_threadpool(
        authenticate_user,
        session=session,
        log_id=req.log_id,
        password=req.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "用户名或密码错误",
            },
        )

    request.state.user_id = user.user_id
    session_id = await create_login_session(
        redis=redis,
        user_id=user.user_id,
        role=user.role,
    )

    # 设置登录会话 Cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    return {"message": "登录成功", "id": user.user_id}
