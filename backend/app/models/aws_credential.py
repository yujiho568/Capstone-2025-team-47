# app/models/aws_credential.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class AwsCredential(Base):
    __tablename__ = "aws_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    access_key_id = Column(String(64), nullable=False)
    secret_access_key = Column(String, nullable=False)

    region = Column(String(32), nullable=True, default="ap-northeast-2")
    name = Column(String(100), nullable=False, default="default")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="aws_credentials", passive_deletes=True)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_awscred_user_name"),
    )
