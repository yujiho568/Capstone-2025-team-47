# app/schemas/credentials.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, constr


# 공통
class AwsCredentialBase(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=100) = "default"
    region: Optional[constr(strip_whitespace=True, max_length=32)] = "ap-northeast-2"
    is_active: bool = True


# 생성 입력
class AwsCredentialCreate(AwsCredentialBase):
    access_key_id: constr(strip_whitespace=True, min_length=8, max_length=64)
    secret_access_key: constr(strip_whitespace=True, min_length=8)  # 평문 저장 (로컬용)


# 부분 업데이트 입력 (키 교체 or 메타 수정)
class AwsCredentialUpdate(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=100)] = None
    region: Optional[constr(strip_whitespace=True, max_length=32)] = None
    is_active: Optional[bool] = None
    access_key_id: Optional[constr(strip_whitespace=True, min_length=8, max_length=64)] = None
    secret_access_key: Optional[constr(strip_whitespace=True, min_length=8)] = None


# 읽기 응답 (민감정보 제외)
class AwsCredentialOut(BaseModel):
    id: int
    user_id: int
    name: str
    region: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None

    # 편의 정보 (민감정보 노출 방지용)
    access_key_id_last4: Optional[str] = Field(
        None, description="Access Key ID 마지막 4자리"
    )
    has_secret: bool = Field(False, description="secret_access_key 존재 여부")

    class Config:
        from_attributes = True  # SQLAlchemy 객체를 바로 serialize
