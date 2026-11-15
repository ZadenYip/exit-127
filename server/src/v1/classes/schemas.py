from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import SQLModel


MAX_PASSPHRASE_LENGTH = 16

_Passphrase = Annotated[
    str | None,
    Field(min_length=1, max_length=MAX_PASSPHRASE_LENGTH),
]

class ClassCreateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=16)
    description: str | None = Field(default=None, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("班级名称不能为空")
        return value


class ClassRead(SQLModel):
    id: int
    name: str
    description: str | None
    teacher_id: int


class ClassDetail(ClassRead):
    member_count: int


class JoinLinkReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passphrase: _Passphrase = None


class JoinLinkRead(BaseModel):
    invite_code: UUID


class JoinClassReq(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_code: str = Field(min_length=1, max_length=64)
    passphrase: _Passphrase = None
