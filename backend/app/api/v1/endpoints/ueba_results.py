# app/api/v1/endpoints/ueba_results.py
from fastapi import APIRouter, Path, Query, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, asc
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from app.db.database import get_db
from app.models.user import User
from app.models.ueba_result import UebaResult
from app.api.v1.endpoints.user import get_current_user

router = APIRouter(prefix="/ueba-results/{user_id}", tags=["ueba-results"])

class UebaResultItem(BaseModel):
    id: int
    timestamp: Optional[datetime]
    initial_session: Optional[bool]
    risk: Optional[float]
    event_name: Optional[str]
    s3_key: str
    source_credential_name: Optional[str] = None

    class Config:
        from_attributes = True

@router.get("", response_model=List[UebaResultItem])
def list_results(
    user_id: int = Path(..., ge=1),
    credential_name: Optional[str] = Query(None, description="선택한 credential 별칭으로 필터링"),
    initial_session: Optional[int] = Query(None, ge=0, le=1, description="0 또는 1"),
    limit: int = Query(100, ge=1, le=1000),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    로그인 사용자의 UEBA 결과를 조회합니다.
    - credential_name: import 당시 기록된 별칭으로 필터 (없으면 전체)
    - initial_session: 0/1 필터 (없으면 전체)
    - limit: 최대 1000
    - order: asc|desc (timestamp 기준)
    """
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    stmt = select(UebaResult).where(UebaResult.user_id == user_id)

    if credential_name:
        stmt = stmt.where(UebaResult.source_credential_name == credential_name)

    if initial_session is not None:
        # DB에는 Boolean일 수 있으니 0/1을 bool로 변환
        stmt = stmt.where(UebaResult.initial_session == bool(initial_session))

    stmt = stmt.order_by(desc(UebaResult.timestamp) if order == "desc" else asc(UebaResult.timestamp))
    stmt = stmt.limit(limit)

    rows = db.execute(stmt).scalars().all()
    # 응답에는 필요한 필드만
    return [
        UebaResultItem(
            id=r.id,
            timestamp=r.timestamp,
            initial_session=r.initial_session,
            risk=r.risk,
            event_name=r.event_name,
            s3_key=r.s3_key,
            source_credential_name=r.source_credential_name,
        )
        for r in rows
    ]
