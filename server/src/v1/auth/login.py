from sqlmodel import Session, select

from v1.auth.bcrypt import verify_password
from v1.auth.models import User
from v1.auth.roles import Role
from v1.auth.session import UserSession


def authenticate_user(
    *, session: Session, log_id: str, password: str
) -> UserSession | None:
    with session.begin():
        user = session.exec(
            select(User.id, User.password_hash, User.role).where(User.login_id == log_id)
        ).one_or_none()

    if user is None:
        return None

    user_id, password_hash, role = user

    if not verify_password(password, password_hash):
        return None

    return UserSession(user_id=user_id, role=Role(role))
