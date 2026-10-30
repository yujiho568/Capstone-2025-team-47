"""All AWS operations run inside Moto. Real ML, SQL, password/JWT and API code."""
import argparse
import json
import os
import secrets
import shutil
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
STATE=ROOT/'.demo'


def prepare_env():
    STATE.mkdir(exist_ok=True)
    # Per-demo application encryption/signing keys, never AWS credentials; don't print.
    from cryptography.fernet import Fernet
    config=STATE/'app-keys.json'
    if not config.exists():
        fd=os.open(config,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f: json.dump(dict(SECRET_KEY=secrets.token_urlsafe(48),FERNET_KEY=Fernet.generate_key().decode()),f)
    os.environ.update(json.loads(config.read_text()))
    os.environ['DATABASE_URL']='sqlite:///'+str(STATE/'web.sqlite')
    os.environ['AWS_EC2_METADATA_DISABLED']='true'


def run(serve=False):
    prepare_env()
    from tools.mock_setup import mock_services
    with mock_services():
        import boto3
        from pipeline.ueba.events import Collector,normalize,digest
        from pipeline.ueba.models import train,Bundle
        from pipeline.ueba.detection import Detector
        from tools.synthetic import generate
        from app.main import app
        from app.db.database import SessionLocal
        from app.models.result_source import ResultSource
        from fastapi.testclient import TestClient
        s3=boto3.client('s3');ddb=boto3.resource('dynamodb')
        table=ddb.create_table(TableName='demo-events',BillingMode='PAY_PER_REQUEST',
            KeySchema=[dict(AttributeName='pk',KeyType='HASH'),dict(AttributeName='sk',KeyType='RANGE')],
            AttributeDefinitions=[dict(AttributeName=n,AttributeType='S') for n in ('pk','sk')])
        for bucket in ('ueba-demo-results','ueba-demo-failures'): s3.create_bucket(Bucket=bucket)
        collector=Collector(table,s3,'ueba-demo-failures')
        inputs=list(generate());receipts=[]
        for event in inputs: receipts.append(collector.collect(event))
        duplicate=collector.collect(inputs[0])
        (STATE/'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in inputs))
        (STATE/'receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in receipts))
        rows=[];kwargs={}
        while True:
            page=table.scan(**kwargs);rows.extend(r for r in page['Items'] if 'eventID' in r)
            if not page.get('LastEvaluatedKey'): break
            kwargs['ExclusiveStartKey']=page['LastEvaluatedKey']
        version='demo-v1';modelroot=STATE/'models'
        if not (modelroot/version).exists():
            training=train(rows,modelroot,version,minimum=100,vec_size=16,min_samples=3)
        else: training={'status':'reused','version':version}
        detector=Detector(table,s3,'ueba-demo-results',Bundle(modelroot,version))
        outcomes=[detector.process(normalize(e)) for e in inputs]
        completed=[o for o in outcomes if o['status']=='complete']
        (STATE/'results').mkdir(exist_ok=True)
        for i,o in enumerate(completed): (STATE/'results'/f'{i:03}.json').write_text(json.dumps(o['payload']))
        with TestClient(app) as client:
            email='demo@example.com';password='local-demo-only-47'
            registration=client.post('/api/v1/users/register',json=dict(email=email,password=password))
            if registration.status_code not in (200,409): raise RuntimeError('demo_registration_failed')
            token_response=client.post('/api/v1/users/login',data=dict(username=email,password=password))
            token_response.raise_for_status()
            auth={'Authorization':'Bearer '+token_response.json()['access_token']}
            uid=client.get('/api/v1/users/me',headers=auth).json()['id']
            creds=client.post(f'/api/v1/credentials/{uid}/store',headers=auth,json=dict(name='demo',
                access_key_id='AKIATESTDEMOONLY',secret_access_key='fake-secret-demo-only',region='us-east-1'))
            if creds.status_code not in (201,409): raise RuntimeError('demo_fake_credential_store_failed')
            with SessionLocal() as db:
                if not db.query(ResultSource).filter_by(user_id=uid,credential_name='demo').first():
                    db.add(ResultSource(user_id=uid,credential_name='demo',bucket='ueba-demo-results',
                        prefix=f"results/realtime/{digest('123456789012:DEMO')}/",principal='123456789012:DEMO'))
                    db.commit()
            response=client.post(f'/api/v1/results/{uid}/import-s3',headers=auth,json=dict(credential_name='demo',max_files=1000))
            response.raise_for_status();summary=response.json()
            fetched=client.get(f'/api/v1/ueba-results/{uid}?limit=1000',headers=auth)
            fetched.raise_for_status()
            report=dict(mode='moto_local_not_aws',synthetic_not_accuracy_evaluation=True,
                input_events=len(inputs),stored=sum(r['status']=='stored' for r in receipts),
                duplicate_replay=duplicate['status'],training=training,results=len(completed),
                insufficient=sum(o['status']=='insufficient_history' for o in outcomes),
                sync=summary,queried=len(fetched.json()))
            (STATE/'report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        if serve:
            import uvicorn
            print('Demo user: demo@example.com / local-demo-only-47; stop: Ctrl-C')
            uvicorn.run(app,host='127.0.0.1',port=8000,log_level='warning')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['run','serve','reset'])
    args=p.parse_args()
    if args.command=='reset':
        if STATE.exists() and not STATE.is_symlink(): shutil.rmtree(STATE)
        print('Removed only .demo local state. Stop the demo server before reset.')
    else: run(args.command=='serve')
