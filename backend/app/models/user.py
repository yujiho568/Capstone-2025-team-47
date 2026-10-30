from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    # Legacy columns retained for non-destructive migration only; no active endpoint reads/writes them.
    aws_access_key = Column(String, nullable=True)
    aws_secret_key = Column(String, nullable=True)  # Legacy data: back up securely, rotate/revoke old keys; never reuse as fallback.
    aws_account_id = Column(String, nullable=True)  # STS get_caller_identity()로 확인한 AWS 계정 ID
    aws_principal_arn = Column(String, nullable=True)  # ex) arn:aws:iam::<account-id>:root

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
