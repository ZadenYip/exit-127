from datetime import datetime
from typing import ClassVar, Optional
from uuid import UUID

from sqlalchemy import BigInteger, Column, ForeignKey, Identity, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PostgreSQLUUID
from sqlmodel import Field, SQLModel


class Class(SQLModel, table=True):
    __tablename__: ClassVar[str] = "classes"

    id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            Identity(start=10000),
            primary_key=True,
        ),
    )
    owner: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id"),
            nullable=False,
        )
    )
    name: str = Field(max_length=16)
    description: str | None = Field(default=None, sa_type=Text)
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(TIMESTAMP(timezone=True, precision=3), nullable=True),
    )


class ClassMember(SQLModel, table=True):
    __tablename__: ClassVar[str] = "class_members"

    class_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("classes.id", ondelete="RESTRICT"),
            primary_key=True,
            nullable=False,
        )
    )
    user_id: int = Field(
        sa_column=Column(BigInteger, primary_key=True, nullable=False)
    )
    joined_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )


class ClassInvite(SQLModel, table=True):
    __tablename__: ClassVar[str] = "class_invites"

    class_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("classes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        )
    )
    invite_code: UUID = Field(
        sa_column=Column(PostgreSQLUUID(as_uuid=True), nullable=False, unique=True)
    )
    passphrase: str | None = Field(default=None, max_length=16)
    expires_at: datetime = Field(
        sa_column=Column(TIMESTAMP(timezone=True, precision=3), nullable=False),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            TIMESTAMP(timezone=True, precision=3),
            nullable=False,
            server_default=text("CURRENT_TIMESTAMP"),
        ),
    )
