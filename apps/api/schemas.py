from pydantic import BaseModel
from typing import Optional


class UserOut(BaseModel):
    id: str
    email: str
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class HealthResponse(BaseModel):
    status: str
    db_connected: Optional[bool] = None
