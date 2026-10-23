from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    username: str
    password: str

class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    password_confirm: str

    @model_validator(mode="after")
    def _same_password(self) -> "SetupRequest":
        if self.password != self.password_confirm:
            raise ValueError("Password tidak sama")
        return self

class SetupStatus(BaseModel):
    needed: bool

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MeResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    admin_id: int | None
    must_change_password: bool

    model_config = {"from_attributes": True}
