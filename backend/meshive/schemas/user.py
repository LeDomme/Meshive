from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "user"] = "user"
    is_active: bool = True
    must_change_password: bool = True

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Username cannot be blank")
        return stripped


class UserUpdate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=1024)
    role: Literal["admin", "user"]
    is_active: bool
    must_change_password: bool = False

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Username cannot be blank")
        return stripped


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    email_verified: bool
    role: Literal["admin", "user"]
    is_active: bool
    must_change_password: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class UserSessionRead(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    browser: str | None
    operating_system: str | None
    device_type: str | None
    is_current: bool


class SessionRevocationResult(BaseModel):
    revoked_count: int


class RecoveryStatus(BaseModel):
    enabled: bool


class PasswordRecoveryRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)

    @field_validator("identifier")
    @classmethod
    def strip_identifier(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Identifier cannot be blank")
        return stripped


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=12, max_length=1024)


class EmailChange(BaseModel):
    email: EmailStr
    current_password: str = Field(min_length=1, max_length=1024)


class AdminEmailVerification(BaseModel):
    email: EmailStr


class ActionTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class ActionMessage(BaseModel):
    message: str
