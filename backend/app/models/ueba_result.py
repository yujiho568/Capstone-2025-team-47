# app/models/ueba_result.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, ForeignKey, UniqueConstraint, Text, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class UebaResult(Base):
    __tablename__ = "ueba_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # NEW: 어떤 credential로 적재되었는지 기록 (별칭)
    source_credential_name = Column(String(100), nullable=True, index=True)

    s3_bucket = Column(String(128), nullable=False)
    s3_key = Column(String(1024), nullable=False, index=True)
    s3_last_modified = Column(DateTime, nullable=True)

    user_id_str = Column(String(128), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=True, index=True)
    event_name = Column(String(128), nullable=True, index=True)
    initial_session = Column(Boolean, nullable=True, index=True)
    embedding_dim = Column(Integer, nullable=True)

    engine = Column(String(64), nullable=True)
    cluster = Column(Integer, nullable=True)
    is_noise = Column(Boolean, nullable=True)
    nearest_dist = Column(Float, nullable=True)
    eps = Column(Float, nullable=True)
    r = Column(Float, nullable=True)
    risk = Column(Float, nullable=True)

    raw_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("s3_bucket", "s3_key", name="uq_uebaresult_s3_object"),
        Index("ix_ueba_results_user_init_ts", "user_id", "initial_session", "timestamp"),
    )
