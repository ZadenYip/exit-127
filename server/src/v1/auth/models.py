from datetime import datetime
from typing import ClassVar

from sqlalchemy import BigInteger, Column, Identity, Integer, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlmodel import Field, SQLModel

from v1.auth.roles import Role


class User(SQLModel, table=True):
    __tablename__: ClassVar[str] = "users"

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, Identity(start=10000), primary_key=True),
    )
    login_id: str = Field(max_length=16, unique=True)
    nickname: str = Field(max_length=16)
    role: Role = Field(sa_type=Integer)
    password_hash: str = Field(max_length=72)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
