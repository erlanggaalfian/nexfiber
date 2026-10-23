from pydantic import BaseModel, computed_field

from app.core.rbac import permissions_for


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: str

    @computed_field
    @property
    def permissions(self) -> list[str]:
        return permissions_for(self.role)

    model_config = {"from_attributes": True}
