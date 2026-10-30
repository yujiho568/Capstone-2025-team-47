from datetime import datetime,timezone
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError,BotoCoreError
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,SecretStr,Field,ConfigDict,model_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.api.v1.endpoints.user import get_current_user
from app.db.database import get_db
from app.models.aws_credential import AwsCredential
from app.core.credentials import encrypt


def owner(user_id:int,current=Depends(get_current_user)):
    if current.id!=user_id: raise HTTPException(403,'Forbidden')
    return current

router=APIRouter(prefix='/credentials/{user_id}',tags=['credentials'],dependencies=[Depends(owner)])

class Input(BaseModel):
    access_key_id: SecretStr = Field(alias='accessKeyId',min_length=8,max_length=128)
    secret_access_key: SecretStr = Field(alias='secretAccessKey',min_length=8,max_length=256)
    session_token: SecretStr | None = Field(None,alias='sessionToken')
    expires_at: datetime | None = Field(None,alias='expiresAt')
    region: str = 'ap-northeast-2'
    name: str = Field('default',min_length=1,max_length=100)
    model_config=ConfigDict(populate_by_name=True,extra='forbid')
    @model_validator(mode='after')
    def expiry(self):
        if self.session_token and (not self.expires_at or not self.expires_at.tzinfo):
            raise ValueError('temporary_credentials_require_expiry')
        if self.expires_at and (not self.session_token or not self.expires_at.tzinfo or self.expires_at<=datetime.now(timezone.utc)):
            raise ValueError('invalid_expiry')
        return self

def identity(payload):
    client=boto3.client('sts',region_name=payload.region,
        aws_access_key_id=payload.access_key_id.get_secret_value(),
        aws_secret_access_key=payload.secret_access_key.get_secret_value(),
        aws_session_token=payload.session_token.get_secret_value() if payload.session_token else None,
        config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':3}))
    try: result=client.get_caller_identity()
    except ClientError as exc:
        code=exc.response['Error']['Code']
        raise HTTPException(403,detail={'code':code}) from None
    except BotoCoreError: raise HTTPException(503,'aws_unavailable') from None
    if result['Arn'].endswith(':root'): raise HTTPException(400,'root_credentials_rejected')
    return result

@router.post('/check')
def check(payload:Input):
    r=identity(payload)
    return dict(account=r['Account'],arn=r['Arn'],userId=r['UserId'],region=payload.region)

@router.post('/store',status_code=201)
def store(payload:Input,user_id:int,db:Session=Depends(get_db)):
    # Encryption configuration is checked before making any AWS request.
    from app.core.credentials import cipher
    try: cipher()
    except ValueError: raise HTTPException(503,'credential_encryption_not_configured') from None
    r=identity(payload)
    data=dict(access_key_id=payload.access_key_id.get_secret_value(),
              secret_access_key=payload.secret_access_key.get_secret_value(),
              session_token=payload.session_token.get_secret_value() if payload.session_token else None,
              expires_at=payload.expires_at.isoformat() if payload.expires_at else None,
              account=r['Account'],arn=r['Arn'])
    row=AwsCredential(user_id=user_id,name=payload.name,region=payload.region,
        access_key_id='****'+data['access_key_id'][-4:],secret_access_key=encrypt(data))
    try: db.add(row); db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback()
        # No unrelated integrity violation is silently called a duplicate.
        if db.query(AwsCredential).filter_by(user_id=user_id,name=payload.name).first():
            raise HTTPException(409,'credential_name_exists') from None
        raise
    return dict(id=row.id,name=row.name,region=row.region,created_at=row.created_at,
                access_key_id_last4=row.access_key_id,has_secret=True)

@router.get('/list')
def listing(user_id:int,db:Session=Depends(get_db)):
    return [dict(name=r.name,region=r.region,created_at=r.created_at,
                 access_key_id_last4=r.access_key_id[-4:],has_secret=True)
            for r in db.query(AwsCredential).filter_by(user_id=user_id).all()]

@router.delete('/{name}')
def delete(user_id:int,name:str,db:Session=Depends(get_db)):
    row=db.query(AwsCredential).filter_by(user_id=user_id,name=name).first()
    if not row: raise HTTPException(404,'credential_not_found')
    db.delete(row); db.commit()
    return {'ok':True}

# Safety boundary: no root keys, caller-selected IAM targets, or live IAM writes.
@router.get('/{name}/quarantine')
@router.post('/{name}/quarantine/apply')
@router.delete('/{name}/quarantine')
def quarantine(user_id:int,name:str,db:Session=Depends(get_db)):
    if not db.query(AwsCredential).filter_by(user_id=user_id,name=name).first():
        raise HTTPException(404,'credential_not_found')
    raise HTTPException(501,'quarantine_disabled_requires_scoped_role_and_target_binding')
