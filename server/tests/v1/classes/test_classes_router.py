from http.cookies import SimpleCookie

import pytest

from tests.conftest import Backend
from v1.auth.session import SESSION_COOKIE_NAME


@pytest.mark.anyio
async def test_revoke_invite_before_creation_returns_not_found(backend: Backend) -> None:
    """验证有效班级从未创建邀请时，撤销返回邀请不存在而非班级不存在。"""
    await register(backend, login_id="revoke-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "无邀请班"})
    assert created.status_code == 201
    class_id = created.json()["id"]
    response = await backend.client.post(f"/v1/classes/{class_id}:revokeJoinLink")
    assert response.status_code == 404
    assert response.json() == {
        "detail": {"code": "INVITE_NOT_FOUND", "message": "邀请已不存在"}
    }


@pytest.mark.anyio
async def test_create_invite_rejects_missing_class(backend: Backend) -> None:
    """验证为不存在的班级创建邀请返回 404。"""
    await register(backend, login_id="invite-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "权限班"})
    assert created.status_code == 201
    class_id = created.json()["id"] + 1
    response = await backend.client.post(f"/v1/classes/{class_id}:createJoinLink", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}}


@pytest.mark.anyio
async def test_create_invite_rejects_deleted_class(backend: Backend) -> None:
    """验证为已软删除的班级创建邀请返回 404。"""
    await register(backend, login_id="invite-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "权限班"})
    assert created.status_code == 201
    class_id = created.json()["id"]
    assert (await backend.client.delete(f"/v1/classes/{class_id}")).status_code == 204
    response = await backend.client.post(f"/v1/classes/{class_id}:createJoinLink", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}}


@pytest.mark.anyio
async def test_create_invite_rejects_other_teachers_class(backend: Backend) -> None:
    """验证老师为非自己的班级创建邀请返回 404。"""
    await register(backend, login_id="invite-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "权限班"})
    assert created.status_code == 201
    class_id = created.json()["id"]
    await register(backend, login_id="invite-other", role=2)
    response = await backend.client.post(f"/v1/classes/{class_id}:createJoinLink", json={})
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}}


@pytest.mark.anyio
async def test_leave_missing_class_returns_not_found(backend: Backend) -> None:
    """验证学生退出不存在的班级返回 404 及班级不存在错误。"""
    await register(backend, login_id="leave-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "退出班"})
    assert created.status_code == 201
    class_id = created.json()["id"] + 1
    await register(backend, login_id="leave-student", role=1)
    response = await backend.client.post(f"/v1/classes/{class_id}:leave")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}}


@pytest.mark.anyio
async def test_leave_deleted_class_returns_not_found(backend: Backend) -> None:
    """验证学生退出已软删除的班级返回 404 及班级不存在错误。"""
    await register(backend, login_id="leave-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "退出班"})
    assert created.status_code == 201
    class_id = created.json()["id"]
    assert (await backend.client.delete(f"/v1/classes/{class_id}")).status_code == 204
    await register(backend, login_id="leave-student", role=1)
    response = await backend.client.post(f"/v1/classes/{class_id}:leave")
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}}


@pytest.mark.anyio
async def test_leave_class_as_non_member_returns_forbidden(backend: Backend) -> None:
    """验证非成员学生退出有效班级返回 403 及非班级成员错误。"""
    await register(backend, login_id="leave-owner", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "退出班"})
    assert created.status_code == 201
    class_id = created.json()["id"]
    await register(backend, login_id="leave-student", role=1)
    response = await backend.client.post(f"/v1/classes/{class_id}:leave")
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "FORBIDDEN", "message": "你不是该班级成员"}}


@pytest.mark.anyio
async def test_admin_cannot_list_classes(backend: Backend) -> None:
    """验证管理员角色访问班级列表时，路由将业务拒绝转换为 403 响应。"""
    from v1.auth.roles import Role
    from v1.auth.session import UserSession, get_current_user

    backend.app.dependency_overrides[get_current_user] = lambda: UserSession(user_id=1, role=Role.ADMIN)
    try:
        response = await backend.client.get("/v1/classes")
        assert response.status_code == 403
        assert response.json() == {"detail": {"code": "FORBIDDEN", "message": "无权访问班级"}}
    finally:
        backend.app.dependency_overrides.pop(get_current_user)


async def register(backend: Backend, *, login_id: str, role: int) -> tuple[int, str]:
    response = await backend.client.post(
        "/v1/auth/register",
        json={"log_id": login_id, "password": "password-123", "role": role},
    )
    assert response.status_code == 200, response.text
    cookie = SimpleCookie()
    cookie.load(response.headers["set-cookie"])
    session_id = cookie[SESSION_COOKIE_NAME].value
    backend.client.cookies.set(SESSION_COOKIE_NAME, session_id)
    return response.json()["id"], session_id


@pytest.mark.anyio
async def test_create_list_and_get_class_api(backend: Backend) -> None:
    """验证创建、列表和详情接口的成功状态码、名称规范化及响应字段一致性。"""
    teacher_id, _ = await register(backend, login_id="class-teacher", role=2)
    created = await backend.client.post(
        "/v1/classes",
        json={"name": "  高一（3）班  ", "description": "班级简介"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "高一（3）班"
    assert body["description"] == "班级简介"
    assert body["teacher_id"] == teacher_id
    class_id = body["id"]

    listed = await backend.client.get("/v1/classes")
    assert listed.status_code == 200
    assert listed.json() == [body]

    detail = await backend.client.get(f"/v1/classes/{class_id}")
    assert detail.status_code == 200
    assert detail.json() == {**body, "member_count": 0}


@pytest.mark.anyio
async def test_invite_join_membership_and_leave_api(backend: Backend) -> None:
    """验证邀请创建、暗号校验、幂等加入、退出、重置和撤销的完整 HTTP 流程。"""
    _, teacher_session = await register(backend, login_id="invite-teacher", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "邀请班"})
    assert created.status_code == 201
    class_id = created.json()["id"]

    invite = await backend.client.post(
        f"/v1/classes/{class_id}:createJoinLink", json={"passphrase": "secret"}
    )
    assert invite.status_code == 201
    invite_code = invite.json()["invite_code"]

    student_id, student_session = await register(
        backend, login_id="invite-student", role=1
    )
    mismatch = await backend.client.post(
        "/v1/classes:join", json={"invite_code": invite_code}
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["code"] == "INVITE_PASSPHRASE_MISMATCH"

    joined = await backend.client.post(
        "/v1/classes:join",
        json={"invite_code": invite_code, "passphrase": "secret"},
    )
    repeated = await backend.client.post(
        "/v1/classes:join",
        json={"invite_code": invite_code, "passphrase": "secret"},
    )
    assert joined.status_code == repeated.status_code == 200
    assert joined.json() is True
    assert repeated.json() is False

    detail = await backend.client.get(f"/v1/classes/{class_id}")
    assert detail.status_code == 200
    assert detail.json()["member_count"] == 1

    left = await backend.client.post(f"/v1/classes/{class_id}:leave")
    assert left.status_code == 204
    assert (await backend.client.get(f"/v1/classes/{class_id}")).status_code == 404

    backend.client.cookies.set(SESSION_COOKIE_NAME, teacher_session)
    reset = await backend.client.post(
        f"/v1/classes/{class_id}:createJoinLink", json={}
    )
    assert reset.status_code == 201
    assert reset.json()["invite_code"] != invite_code
    revoked = await backend.client.post(f"/v1/classes/{class_id}:revokeJoinLink")
    assert revoked.status_code == 204
    repeated_revoke = await backend.client.post(
        f"/v1/classes/{class_id}:revokeJoinLink"
    )
    assert repeated_revoke.status_code == 404
    assert repeated_revoke.json() == {
        "detail": {"code": "INVITE_NOT_FOUND", "message": "邀请已不存在"}
    }
    missing_revoke = await backend.client.post(
        f"/v1/classes/{class_id + 1}:revokeJoinLink"
    )
    assert missing_revoke.status_code == 404
    assert missing_revoke.json() == {
        "detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}
    }

    backend.client.cookies.set(SESSION_COOKIE_NAME, student_session)
    invalidated = await backend.client.post(
        "/v1/classes:join", json={"invite_code": reset.json()["invite_code"]}
    )
    assert invalidated.status_code == 404
    assert invalidated.json()["detail"]["code"] == "INVITE_NOT_FOUND"


@pytest.mark.anyio
async def test_delete_missing_class_returns_not_found(backend: Backend) -> None:
    """验证老师删除不存在的班级返回 404 及班级不存在错误。"""
    await register(backend, login_id="del-miss-t", role=2)
    created = await backend.client.post("/v1/classes", json={"name": "参照班"})
    assert created.status_code == 201
    missing_class_id = created.json()["id"] + 1

    response = await backend.client.delete(f"/v1/classes/{missing_class_id}")
    assert response.status_code == 404
    assert response.json() == {
        "detail": {"code": "CLASS_NOT_FOUND", "message": "班级不存在"}
    }


@pytest.mark.anyio
async def test_class_api_role_access_and_soft_delete(backend: Backend) -> None:
    """验证角色权限、无权查看返回 404，以及软删除后列表和详情隐藏班级。"""
    teacher_id, teacher_session = await register(
        backend, login_id="delete-teacher", role=2
    )
    created = await backend.client.post("/v1/classes", json={"name": "删除班"})
    class_id = created.json()["id"]

    # 这里注册后 client 是学生
    student_id, student_session = await register(
        backend, login_id="delete-student", role=1
    )
    
    forbidden_create = await backend.client.post(
        "/v1/classes", json={"name": "越权创建"}
    )
    assert forbidden_create.status_code == 403
    assert forbidden_create.json()["detail"]["code"] == "FORBIDDEN"
    assert (await backend.client.get(f"/v1/classes/{class_id}")).status_code == 404

    backend.client.cookies.set(SESSION_COOKIE_NAME, teacher_session)
    deleted = await backend.client.delete(f"/v1/classes/{class_id}")
    assert deleted.status_code == 204
    assert (await backend.client.get("/v1/classes")).json() == []
    assert (await backend.client.get(f"/v1/classes/{class_id}")).status_code == 404

    backend.client.cookies.set(SESSION_COOKIE_NAME, teacher_session)
    forbidden_join = await backend.client.post(
        "/v1/classes:join", json={"invite_code": "not-a-link"}
    )
    assert forbidden_join.status_code == 403
    backend.client.cookies.set(SESSION_COOKIE_NAME, student_session)
    assert student_id != teacher_id


@pytest.mark.anyio
async def test_class_api_requires_auth(backend: Backend) -> None:
    """验证未登录访问班级列表返回 401。"""
    backend.client.cookies.clear()
    unauthenticated = await backend.client.get("/v1/classes")
    assert unauthenticated.status_code == 401


@pytest.mark.anyio
async def test_class_api_validates_inputs(backend: Backend) -> None:
    """验证非法名称、额外字段和非正数班级 ID 返回 422。"""
    await register(backend, login_id="valid-teacher", role=2)
    for payload in (
        {"name": "  "},
        {"name": "N" * 17},
        {"name": "有效班", "unexpected": True},
    ):
        response = await backend.client.post("/v1/classes", json=payload)
        assert response.status_code == 422
    assert (await backend.client.get("/v1/classes/0")).status_code == 422

