from typing import ClassVar

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"

    id: int | None = Field(default=None, primary_key=True)
    login_id: str = Field(max_length=16, unique=True)
    nickname: str = Field(max_length=16)
    role: int
    password_hash: str = Field(max_length=72)
