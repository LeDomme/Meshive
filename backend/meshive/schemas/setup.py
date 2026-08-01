from pydantic import BaseModel, Field, field_validator


class SetupStatus(BaseModel):
    required: bool
    enabled: bool


class InitialAdminCreate(BaseModel):
    setup_token: str = Field(min_length=1, max_length=1024)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=1024)

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Username cannot be blank")
        return stripped
