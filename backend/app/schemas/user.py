from pydantic import BaseModel, EmailStr, Field, ConfigDict, SecretStr, field_validator
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: SecretStr = Field(min_length=8,max_length=72)
    model_config=ConfigDict(extra='forbid')
    @field_validator('password')
    @classmethod
    def password_bytes(cls,value):
        if len(value.get_secret_value().encode())>72: raise ValueError('password_too_long')
        return value
class UserRead(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime
    model_config=ConfigDict(from_attributes=True)
class Token(BaseModel):
    access_token: str
    token_type: str
class UserLogin(BaseModel):
    email: EmailStr
    password: SecretStr
