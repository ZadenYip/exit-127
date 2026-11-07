from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from error.handlers import register_exception_handlers
from v1.auth.deps import get_user_service
from v1.auth.error.errors import LoginIdAlreadyExistsError
from v1.auth.roles import Role
from v1.auth.router import router as auth_router
from v1.auth.session import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    UserSession,
)


class StubUserService:
    def __init__(self) -> None:
        self.register_result: tuple[int, str] = (12345, "register-session")
        self.register_error: Exception | None = None
        self.authenticated_user: UserSession | None = UserSession(
            user_id=12345,
            role=Role.STUDENT,
        )
        self.login_session_id = "login-session"
        self.register_calls: list[dict[str, object]] = []
        self.authenticate_calls: list[dict[str, object]] = []
        self.create_session_calls: list[dict[str, object]] = []

    async def register(self, **kwargs: object) -> tuple[int, str]:
        self.register_calls.append(kwargs)
        if self.register_error is not None:
            raise self.register_error
        return self.register_result

    async def authenticate(self, **kwargs: object) -> UserSession | None:
        self.authenticate_calls.append(kwargs)
        return self.authenticated_user

    async def create_login_session(self, **kwargs: object) -> str:
        self.create_session_calls.append(kwargs)
        return self.login_session_id


@pytest.fixture
def client_and_service() -> Iterator[tuple[TestClient, StubUserService]]:
    service = StubUserService()
    app = FastAPI()
    app.include_router(auth_router, prefix="/v1")
    register_exception_handlers(app)
    app.dependency_overrides[get_user_service] = lambda: service

    with TestClient(app) as client:
        yield client, service


# 测试注册成功时返回用户 ID，并设置包含安全属性的登录会话 Cookie。
def test_register_success_sets_session_cookie(
    client_and_service: tuple[TestClient, StubUserService],
) -> None:
    client, service = client_and_service

    response = client.post(
        "/v1/auth/register",
        json={"log_id": "student1", "password": "password1", "role": 1},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "注册成功", "id": 12345}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=register-session")
    assert f"Max-Age={SESSION_TTL_SECONDS}" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert service.register_calls == [
        {"log_id": "student1", "password": "password1", "role": Role.STUDENT}
    ]


# 测试登录 ID 已存在时返回 409，且不签发登录会话 Cookie。
def test_register_duplicate_login_id_returns_conflict(
    client_and_service: tuple[TestClient, StubUserService],
) -> None:
    client, service = client_and_service
    service.register_error = LoginIdAlreadyExistsError()

    response = client.post(
        "/v1/auth/register",
        json={"log_id": "student1", "password": "password1", "role": 1},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LOGIN_ID_ALREADY_EXISTS"
    assert "set-cookie" not in response.headers


# 测试凭证正确时登录成功、创建会话，并返回安全属性完整的 Cookie。
def test_login_success_sets_session_cookie(
    client_and_service: tuple[TestClient, StubUserService],
) -> None:
    client, service = client_and_service

    response = client.post(
        "/v1/auth/login",
        json={"log_id": "student1", "password": "password1"},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "登录成功", "id": 12345}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=login-session")
    assert f"Max-Age={SESSION_TTL_SECONDS}" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert service.authenticate_calls == [
        {"log_id": "student1", "password": "password1"}
    ]
    assert service.create_session_calls == [
        {"user_id": 12345, "role": Role.STUDENT}
    ]


# 测试凭证错误时返回 401，且不会创建会话或设置 Cookie。
def test_login_invalid_credentials_returns_unauthorized(
    client_and_service: tuple[TestClient, StubUserService],
) -> None:
    client, service = client_and_service
    service.authenticated_user = None

    response = client.post(
        "/v1/auth/login",
        json={"log_id": "student1", "password": "wrongpass"},
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers
    assert service.create_session_calls == []
