from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.v1.endpoints.credentials import owner
from app.models.result_source import ResultSource
from app.schemas.results import ImportS3Request,ImportS3Summary
from app.services.s3_import import get_stored_credentials,make_s3_client,import_s3_jsons,SourceFailure
from app.core.credentials import decrypt

router=APIRouter(prefix='/results/{user_id}',tags=['results'],dependencies=[Depends(owner)])

@router.post('/import-s3',response_model=ImportS3Summary)
def import_from_s3(payload:ImportS3Request,user_id:int,db:Session=Depends(get_db)):
    source=db.query(ResultSource).filter_by(user_id=user_id,credential_name=payload.credential_name).first()
    if not source: raise HTTPException(409,'operator_result_source_binding_required')
    try:
        cred=get_stored_credentials(db,user_id,payload.credential_name)
        data=decrypt(cred.secret_access_key)
        return import_s3_jsons(db,user_id,source,make_s3_client(cred.region,data),
                              payload.max_files,payload.continuation_token,payload.dry_run)
    except ValueError as exc:
        raise HTTPException(409,str(exc)) from None
    except SourceFailure as exc:
        raise HTTPException(503,detail={'code':exc.code}) from None
