import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from sqlalchemy.exc import IntegrityError
from botocore.exceptions import ClientError
from app.models.user import User
from app.models.ueba_result import UebaResult
from app.models.result_source import ResultSource
from app.services.s3_import import import_s3_jsons,SourceFailure,aws_reason
from app.core.credentials import encrypt,decrypt
from app.schemas.results import ResultPayload


def login(client,email='one@example.com'):
    response=client.post('/api/v1/users/register',json=dict(email=email,password='testpassword47'))
    assert response.status_code==200,response.text
    uid=response.json()['id']
    token=client.post('/api/v1/users/login',data=dict(username=email,password='testpassword47')).json()['access_token']
    return uid,{'Authorization':'Bearer '+token}

def payload(**changes):
    p=dict(ok=True,eventID='event-1',userId='123456789012:ALICE',timestamp='2026-01-01T00:00:00Z',eventName='ListBuckets',
           modelVersion='v1',initial_session=True,embedding_dim=16,result=dict(engine='ocsvm',risk=45.0,score=.1,is_anomaly=False))
    p.update(changes);return p

def test_no_auth_and_cross_owner(api):
    client,_=api;uid,auth=login(client);other,_=login(client,'two@example.com')
    requests=[('POST',f'/results/{other}/import-s3',{}),('POST',f'/credentials/{other}/store',{}),
              ('POST',f'/credentials/{other}/check',{}),('GET',f'/credentials/{other}/list',None),
              ('DELETE',f'/credentials/{other}/name',None),('GET',f'/ueba-results/{other}',None),
              ('POST',f'/credentials/{other}/name/quarantine/apply',None),
              ('GET',f'/credentials/{other}/name/quarantine',None),('DELETE',f'/credentials/{other}/name/quarantine',None)]
    for method,path,data in requests:
        assert client.request(method,'/api/v1'+path,json=data).status_code==401
        assert client.request(method,'/api/v1'+path,json=data,headers=auth).status_code==403
    assert 'aws_access_key' not in client.get('/api/v1/users/me',headers=auth).json()
    assert client.post(f'/api/v1/results/{uid}/import-s3',json={'bucket':'other','prefix':'private/'},headers=auth).status_code==422

def test_credentials_fail_closed_and_no_echo(api,aws,monkeypatch):
    client,factory=api;uid,auth=login(client)
    body=dict(name='demo',access_key_id='AKIATESTONLY47',secret_access_key='fake-secret-test-only')
    from app.core.config import get_settings
    settings=get_settings();key=settings.FERNET_KEY
    monkeypatch.setattr(settings,'FERNET_KEY',None)
    assert client.post(f'/api/v1/credentials/{uid}/store',json=body,headers=auth).status_code==503
    monkeypatch.setattr(settings,'FERNET_KEY',key)
    assert client.post(f'/api/v1/credentials/{uid}/store',json=body,headers=auth).status_code==201
    from app.models.aws_credential import AwsCredential
    with factory() as db:
        cred=db.query(AwsCredential).first()
        assert body['secret_access_key'] not in cred.secret_access_key
        assert decrypt(cred.secret_access_key)['access_key_id']==body['access_key_id']
    # Rejected input response cannot echo secret material.
    body['unexpected']='fake-sensitive-value'
    response=client.post(f'/api/v1/credentials/{uid}/store',json=body,headers=auth)
    assert response.status_code==422 and 'fake-sensitive-value' not in response.text
    with pytest.raises(ValueError): decrypt('legacy-plaintext')
    from datetime import datetime,timedelta,timezone
    with pytest.raises(ValueError): decrypt(encrypt({'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}))

def test_partial_repeated_changed_and_concurrent_sync(api,aws):
    client,factory=api;uid,_=login(client);_,s3=aws
    source=SimpleNamespace(bucket='ueba-results',prefix='results/',principal='123456789012:ALICE',credential_name='demo')
    def put(key,p): s3.put_object(Bucket=source.bucket,Key='results/'+key,Body=json.dumps(p))
    put('good.json',payload());s3.put_object(Bucket=source.bucket,Key='results/bad.json',Body='{broken')
    with factory() as db:
        result=import_s3_jsons(db,uid,source,s3)
        assert (result['imported'],result['errors'],result['status'])==(1,1,'partial_failure')
        assert result['continuation_token'] is None
    s3.delete_object(Bucket=source.bucket,Key='results/bad.json')
    def sync(_):
        with factory() as db: return import_s3_jsons(db,uid,source,s3)
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(sync,range(3)))
    assert sum(r['skipped_existing'] for r in results)==3
    with factory() as db: assert db.query(UebaResult).count()==1
    put('good.json',payload(eventName='Changed'))
    assert sync(0)['failures'][0]['reason']=='immutable_object_changed'
    # Concurrent *first* insert too.
    put('new.json',payload(eventID='event-2'))
    with ThreadPoolExecutor(max_workers=3) as pool: list(pool.map(sync,range(3)))
    with factory() as db: assert db.query(UebaResult).count()==2

def test_schema_risk_and_storage_not_empty_success(api):
    for bad in (dict(result=dict(engine='ocsvm',risk=101)),dict(initial_session='false'),dict(timestamp='nonsense'),dict(embedding_dim=0)):
        with pytest.raises(ValueError): ResultPayload.model_validate(payload(**bad))
    s3=Mock();s3.list_objects_v2.side_effect=RuntimeError('network down')
    with pytest.raises(SourceFailure,match=''):
        import_s3_jsons(Mock(),1,SimpleNamespace(bucket='x',prefix='y'),s3)
    expected={'ExpiredToken':'credentials_expired','InvalidAccessKeyId':'credentials_invalid','AccessDenied':'access_denied','SlowDown':'temporary_aws_error'}
    for code,reason in expected.items(): assert aws_reason(ClientError({'Error':{'Code':code}},'GetObject'))==reason

def test_unrelated_integrity_is_failure(api,aws):
    _,factory=api;_,s3=aws
    source=SimpleNamespace(bucket='ueba-results',prefix='results/',principal='123456789012:ALICE',credential_name='demo')
    s3.put_object(Bucket=source.bucket,Key='results/good.json',Body=json.dumps(payload()))
    # Foreign key violation: user 999 doesn't exist. Must never count as duplicate.
    with factory() as db:
        with pytest.raises(SourceFailure) as exc: import_s3_jsons(db,999,source,s3)
        assert exc.value.code=='database_integrity_error'

def test_bounded_page_continuation_and_wrong_principal(api,aws):
    client,factory=api;uid,_=login(client);_,s3=aws
    source=SimpleNamespace(bucket='ueba-results',prefix='results/',principal='123456789012:ALICE',credential_name='demo')
    for i in range(3): s3.put_object(Bucket=source.bucket,Key=f'results/{i}.json',Body=json.dumps(payload(eventID=f'event-{i}')))
    with factory() as db:
        page=import_s3_jsons(db,uid,source,s3,max_files=2)
        assert page['scanned']==2 and page['continuation_token']
        next_page=import_s3_jsons(db,uid,source,s3,max_files=2,continuation_token=page['continuation_token'])
        assert next_page['scanned']==1 and next_page['continuation_token'] is None
    s3.put_object(Bucket=source.bucket,Key='results/other.json',Body=json.dumps(payload(userId='OTHER')))
    with factory() as db:
        r=import_s3_jsons(db,uid,source,s3)
        assert r['errors']==1 and r['failures'][0]['reason']=='principal_mismatch'

def test_temporary_credential_registration_and_root_rejection(api,aws,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.models.aws_credential import AwsCredential
    client,factory=api;uid,auth=login(client)
    body=dict(name='temporary',access_key_id='ASIATESTONLY47',secret_access_key='fake-secret-test-only',
              session_token='fake-session-token-test-only',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
    response=client.post(f'/api/v1/credentials/{uid}/store',json=body,headers=auth)
    assert response.status_code==201,response.text
    with factory() as db:
        data=decrypt(db.query(AwsCredential).filter_by(name='temporary').one().secret_access_key)
        assert data['session_token']=='fake-session-token-test-only' and data['expires_at']
    del body['expires_at']
    assert client.post(f'/api/v1/credentials/{uid}/check',json=body,headers=auth).status_code==422
    del body['session_token']
    from app.api.v1.endpoints import credentials
    fake=Mock();fake.get_caller_identity.return_value=dict(Account='123456789012',Arn='arn:aws:iam::123456789012:root',UserId='root')
    monkeypatch.setattr(credentials.boto3,'client',lambda *a,**k:fake)
    assert client.post(f'/api/v1/credentials/{uid}/check',json=body,headers=auth).status_code==400
