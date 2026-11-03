from typing import ClassVar

from sqlalchemy import Integer
from sqlmodel import Field, SQLModel

from v1.auth.roles import Role


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"

    id: int = Field(primary_key=True)
    login_id: str = Field(max_length=16, unique=True)
    nickname: str = Field(max_length=16)
    role: Role = Field(sa_type=Integer)
    password_hash: str = Field(max_length=72)
