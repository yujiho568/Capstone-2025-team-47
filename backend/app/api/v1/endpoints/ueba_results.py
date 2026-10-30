import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter,Path,Query,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select,desc,asc
from pydantic import BaseModel,ConfigDict
from app.db.database import get_db
from app.models.user import User
from app.models.ueba_result import UebaResult
from app.api.v1.endpoints.user import get_current_user

router=APIRouter(prefix='/ueba-results/{user_id}',tags=['ueba-results'])

class UebaResultItem(BaseModel):
    id:int
    timestamp:Optional[datetime]
    initial_session:Optional[bool]
    risk:Optional[float]
    event_name:Optional[str]
    s3_key:str
    source_credential_name:Optional[str]=None
    event_id:Optional[str]=None
    model_version:Optional[str]=None
    analysis_kind:str='legacy'
    analysis_version:Optional[str]=None
    supersedes_key:Optional[str]=None
    input_event_ids:Optional[list[str]]=None
    model_config=ConfigDict(from_attributes=True,protected_namespaces=())

@router.get('',response_model=list[UebaResultItem])
def list_results(user_id:int=Path(...,ge=1),credential_name:Optional[str]=None,
                 initial_session:Optional[int]=Query(None,ge=0,le=1),
                 limit:int=Query(100,ge=1,le=1000),order:str=Query('desc',pattern='^(asc|desc)$'),
                 db:Session=Depends(get_db),current_user:User=Depends(get_current_user)):
    if current_user.id!=user_id: raise HTTPException(403,'Forbidden')
    stmt=select(UebaResult).where(UebaResult.user_id==user_id)
    if credential_name: stmt=stmt.where(UebaResult.source_credential_name==credential_name)
    if initial_session is not None: stmt=stmt.where(UebaResult.initial_session==bool(initial_session))
    stmt=stmt.order_by(desc(UebaResult.timestamp) if order=='desc' else asc(UebaResult.timestamp),UebaResult.id).limit(limit)
    output=[]
    for row in db.execute(stmt).scalars():
        raw=json.loads(row.raw_json or '{}')
        output.append(UebaResultItem(id=row.id,timestamp=row.timestamp,initial_session=row.initial_session,
            risk=row.risk,event_name=row.event_name,s3_key=row.s3_key,source_credential_name=row.source_credential_name,
            event_id=raw.get('eventID'),model_version=raw.get('modelVersion'),
            analysis_kind=raw.get('analysisKind','legacy'),analysis_version=raw.get('analysisVersion'),
            supersedes_key=raw.get('supersedesKey'),input_event_ids=raw.get('inputEventIDs')))
    return output
