from sqlalchemy import Column,Integer,String,ForeignKey,UniqueConstraint
from app.db.database import Base

class ResultSource(Base):
    """Operator-provisioned binding; no browser API creates these trust boundaries."""
    __tablename__='result_sources'
    id=Column(Integer,primary_key=True)
    user_id=Column(Integer,ForeignKey('users.id'),nullable=False)
    credential_name=Column(String(100),nullable=False)
    bucket=Column(String(128),nullable=False)
    prefix=Column(String(1024),nullable=False)
    principal=Column(String(512),nullable=False)
    __table_args__=(UniqueConstraint('user_id','credential_name'),UniqueConstraint('bucket','prefix'))
