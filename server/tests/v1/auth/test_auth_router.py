import json
from http.cookies import SimpleCookie

import pytest
from sqlalchemy import text

from tests.conftest import Backend
from v1.auth.session import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS


def assert_session_cookie(response) -> str:
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    morsel = cookie[SESSION_COOKIE_NAME]

    assert int(morsel["max-age"]) == SESSION_TTL_SECONDS
    assert morsel["path"] == "/"
    assert morsel["secure"]
    assert morsel["httponly"]
    assert morsel["samesite"] == "strict"
    return morsel.value


@pytest.mark.anyio
async def test_register_creates_user_and_login_session(backend: Backend) -> None:
    """应能注册新用户并创建登录会话。"""
    response = await backend.client.post(
        "/v1/auth/register",
        json={"log_id": "student-01", "password": "password-123", "role": 1},
    )

    assert response.status_code == 200
    body = response.json()
    session_id = assert_session_cookie(response)
    assert body["message"]
    assert body["id"] >= 10000

    async with backend.engine.connect() as connection:
        user = (
            await connection.execute(
                text(
                    "SELECT login_id, nickname, role, password_hash "
                    "FROM users WHERE id = :id"
                ),
                {"id": body["id"]},
            )
        ).one()
    assert user.login_id == user.nickname == "student-01"
    assert user.role == 1
    assert user.password_hash != "password-123"

    session_data = await backend.redis.get(session_id)
    assert session_data is not None
    session = json.loads(session_data)
    assert session["user_id"] == body["id"]
    assert session["role"] == 1
    assert await backend.redis.ttl(session_id) > 0


@pytest.mark.anyio
async def test_register_rejects_duplicate_login_id(backend: Backend) -> None:
    """尝试注册重复登录 ID 的用户时应返回冲突错误。"""
    payload = {"log_id": "duplicate-01", "password": "password-123", "role": 1}
    first = await backend.client.post("/v1/auth/register", json=payload)

    second = await backend.client.post("/v1/auth/register", json=payload)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "LOGIN_ID_ALREADY_EXISTS"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"log_id": "ab", "password": "password-123", "role": 1},
        {"log_id": "student-02", "password": "short", "role": 1},
        {"log_id": "student-03", "password": "password-123", "role": 3},
        {"log_id": "student-04", "password": "password-123"},
    ],
)
async def test_register_validates_request(payload: dict, backend: Backend) -> None:
    """会拒绝不符合要求的注册请求。"""
    response = await backend.client.post("/v1/auth/register", json=payload)

    assert response.status_code == 422


@pytest.mark.anyio
async def test_login_sets_session_cookie_for_valid_credentials(backend: Backend) -> None:
    """应能使用有效的登录凭据登录并设置会话 Cookie。"""
    registration = await backend.client.post(
        "/v1/auth/register",
        json={"log_id": "teacher-01", "password": "password-123", "role": 2},
    )
    backend.client.cookies.clear()

    response = await backend.client.post(
        "/v1/auth/login",
        json={"log_id": "teacher-01", "password": "password-123"},
    )

    assert registration.status_code == 200
    assert response.status_code == 200
    assert response.json()["id"] == registration.json()["id"]
    session_id = assert_session_cookie(response)
    session_data = await backend.redis.get(session_id)
    assert session_data is not None
    session = json.loads(session_data)
    assert session["user_id"] == response.json()["id"]
    assert session["role"] == 2


@pytest.mark.anyio
@pytest.mark.parametrize("log_id,password", [("unknown-01", "password-123"), ("student-01", "wrong-pass")])
async def test_login_rejects_unknown_user_or_wrong_password(
    log_id: str, password: str, backend: Backend
) -> None:
    """应拒绝未知用户或错误密码的登录请求。"""
    await backend.client.post(
        "/v1/auth/register",
        json={"log_id": "student-01", "password": "password-123", "role": 1},
    )
    backend.client.cookies.clear()

    response = await backend.client.post(
        "/v1/auth/login", json={"log_id": log_id, "password": password}
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_CREDENTIALS"
    assert "set-cookie" not in response.headers


@pytest.mark.anyio
async def test_login_validates_request(backend: Backend) -> None:
    """会拒绝不符合要求的登录请求。"""
    response = await backend.client.post(
        "/v1/auth/login", json={"log_id": "ab", "password": "short"}
    )

    assert response.status_code == 422
