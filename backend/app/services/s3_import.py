import json
from datetime import datetime,timezone
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from app.models.aws_credential import AwsCredential
from app.models.ueba_result import UebaResult
from app.schemas.results import ResultPayload

class SourceFailure(RuntimeError):
    def __init__(self,code): self.code=code

def aws_reason(exc):
    code=exc.response['Error']['Code']
    if code in ('ExpiredToken','ExpiredTokenException','RequestExpired'): return 'credentials_expired'
    if code in ('InvalidAccessKeyId','InvalidClientTokenId','SignatureDoesNotMatch'): return 'credentials_invalid'
    if code in ('AccessDenied','AccessDeniedException'): return 'access_denied'
    if code in ('SlowDown','Throttling','ServiceUnavailable','InternalError','RequestTimeout'): return 'temporary_aws_error'
    return 'aws_object_error'

def get_stored_credentials(db,user_id,credential_name):
    row=db.query(AwsCredential).filter_by(user_id=user_id,name=credential_name).first()
    if not row: raise ValueError('credential_not_found')
    return row

def make_s3_client(region,data):
    return boto3.client('s3',region_name=region,aws_access_key_id=data['access_key_id'],
        aws_secret_access_key=data['secret_access_key'],aws_session_token=data.get('session_token'),
        config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':3,'mode':'standard'}))

def map_payload_to_model(user_id,bucket,key,last_modified,payload,source_credential_name=None):
    r=payload['result']
    return UebaResult(user_id=user_id,source_credential_name=source_credential_name,
        s3_bucket=bucket,s3_key=key,s3_last_modified=last_modified,user_id_str=payload['userId'],
        timestamp=datetime.fromisoformat(payload['timestamp'].replace('Z','+00:00')),
        event_name=payload['eventName'],initial_session=payload['initial_session'],
        embedding_dim=payload['embedding_dim'],engine=r['engine'],risk=r['risk'],
        cluster=r.get('cluster'),is_noise=r.get('is_noise'),nearest_dist=r.get('nearest_dist'),
        eps=r.get('eps'),r=r.get('r'),raw_json=json.dumps(payload,sort_keys=True,allow_nan=False))

def import_s3_jsons(db,user_id,source,s3,max_files=100,continuation_token=None,dry_run=False):
    """One bounded page / one transaction, SAVEPOINT per valid object.

    Unique conflict is accepted only after comparing the existing owner's canonical
    payload. Changed content at a fixed key is a failure under immutable policy.
    """
    args=dict(Bucket=source.bucket,Prefix=source.prefix,MaxKeys=max_files)
    if continuation_token: args['ContinuationToken']=continuation_token
    try: page=s3.list_objects_v2(**args)
    except ClientError as exc: raise SourceFailure(aws_reason(exc)) from None
    except Exception: raise SourceFailure('storage_unavailable') from None
    summary=dict(scanned=0,imported=0,skipped_existing=0,errors=0,failures=[],
                 continuation_token=None,synced_at=datetime.now(timezone.utc),status='success')
    publication_cache={}
    for obj in page.get('Contents',[]):
        key=obj['Key']
        if not key.endswith('.json'): continue
        summary['scanned']+=1
        try:
            response=s3.get_object(Bucket=source.bucket,Key=key)
            if response.get('ContentLength',0)>1024*1024: raise ValueError('object_too_large')
            body=response['Body'].read(1024*1024+1)
            if len(body)>1024*1024: raise ValueError('object_too_large')
            payload=json.loads(body,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non_finite_json')))
            ResultPayload.model_validate(payload)
            if payload['userId']!=source.principal: raise ValueError('principal_mismatch')
            if payload.get('analysisKind')=='reanalysis':
                from app.services.analysis_publication import verify_publication
                verify_publication(s3,source.bucket,source.principal,key,payload,publication_cache)
            canonical=json.dumps(payload,sort_keys=True,allow_nan=False)
            if dry_run: continue
            row=map_payload_to_model(user_id,source.bucket,key,obj.get('LastModified'),payload,source.credential_name)
            try:
                with db.begin_nested(): db.add(row); db.flush()
                summary['imported']+=1
            except IntegrityError:
                existing=db.query(UebaResult).filter_by(s3_bucket=source.bucket,s3_key=key).first()
                if existing is None: raise  # FK/NOT NULL/other errors are not duplicates.
                if existing.user_id!=user_id or existing.raw_json!=canonical:
                    raise ValueError('immutable_object_changed')
                summary['skipped_existing']+=1
        except ClientError as exc:
            reason=aws_reason(exc)
            summary['failures'].append(dict(key=key,reason=reason))
        except (ValueError,TypeError,UnicodeDecodeError,ValidationError) as exc:
            reason=str(exc) if str(exc) in ('object_too_large','principal_mismatch','immutable_object_changed','analysis_run_incomplete','invalid_analysis_lineage') else 'invalid_result_json_or_schema'
            summary['failures'].append(dict(key=key,reason=reason))
        except IntegrityError:
            db.rollback(); raise SourceFailure('database_integrity_error') from None
        except Exception:
            db.rollback(); raise SourceFailure('database_or_storage_unavailable') from None
    try:
        if not dry_run: db.commit()
    except Exception:
        db.rollback(); raise SourceFailure('database_commit_failed') from None
    summary['errors']=len(summary['failures'])
    if summary['errors']: summary['status']='partial_failure'
    else: summary['continuation_token']=page.get('NextContinuationToken')
    return summary
