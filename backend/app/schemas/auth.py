from datetime import datetime
from uuid import UUID

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email = value.strip().casefold()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Invalid email")
        return email


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str | None
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    permissions: list[str] | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    organization: str | None
    title: str | None
    status: str
    role_codes: list[str]
    permissions: list[str]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)
    full_name: str = Field(min_length=1, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    status: str = Field(default="active", max_length=32)
    role_codes: list[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=200)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    organization: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=32)
    role_codes: list[str] | None = None
