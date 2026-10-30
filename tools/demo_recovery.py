"""Synthetic local recovery -> late-event correction -> authenticated web DB demo.

Moto supplies AWS APIs. Lambda invocation is an explicit in-process adapter,
Streams delivery is a direct Detector call; neither is a managed AWS retry test.
"""
import argparse,copy,importlib.util,io,json,os,secrets,sys
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'backend')]


def run(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    from cryptography.fernet import Fernet
    os.environ.update(SECRET_KEY=secrets.token_urlsafe(48),FERNET_KEY=Fernet.generate_key().decode(),
        DATABASE_URL='sqlite:///'+str(output/'web.sqlite'),USER_EVENT_TABLE='recovery-events',FAILURE_BUCKET='recovery-demo-failures')
    from tools.mock_setup import mock_services
    with mock_services():
        import boto3
        from tools.synthetic import generate
        from tools.replay import ReplayConfig,receive_and_replay
        from pipeline.ueba.events import Collector,normalize,digest
        from pipeline.ueba.models import train,Bundle
        from pipeline.ueba.detection import Detector
        from pipeline.ueba.reanalysis import make_snapshot,plan_reanalysis,execute_reanalysis,get_json
        table=boto3.resource('dynamodb').create_table(TableName='recovery-events',BillingMode='PAY_PER_REQUEST',
            KeySchema=[dict(AttributeName='pk',KeyType='HASH'),dict(AttributeName='sk',KeyType='RANGE')],
            AttributeDefinitions=[dict(AttributeName=k,AttributeType='S') for k in ('pk','sk')])
        s3=boto3.client('s3');sqs=boto3.client('sqs')
        for name in ('recovery-demo-results','recovery-demo-failures'): s3.create_bucket(Bucket=name)
        bucket='recovery-demo-results';collector=Collector(table,s3,'recovery-demo-failures')
        events=list(generate(120));late=events[25];before=[normalize(e) for i,e in enumerate(events) if i!=25]
        for i,e in enumerate(events):
            if i!=25: collector.collect(e)
        training=train(before,output/'models','recovery-model-v1',minimum=100,vec_size=16,min_samples=3)
        bundle=Bundle(output/'models','recovery-model-v1');detector=Detector(table,s3,bucket,bundle)
        for row in before: detector.process(row)
        path=ROOT/'pipeline/UEBA/modules/ct-ingest/collector/event_collector.py'
        spec=importlib.util.spec_from_file_location('recovery_collector',path);handler=importlib.util.module_from_spec(spec);spec.loader.exec_module(handler)
        receipts=[]
        class LocalLambda:
            def invoke(self,**kwargs):
                result=handler.handler(json.loads(kwargs['Payload']),None);receipts.append(result)
                return dict(StatusCode=200,Payload=io.BytesIO(json.dumps(result).encode()))
        queue_reports=[]
        for label,body in [('delivery',late),('execution',dict(requestPayload=late,responseContext={'functionError':'Unhandled'}))]:
            url=sqs.create_queue(QueueName='recovery-'+label)['QueueUrl']
            sqs.send_message(QueueUrl=url,MessageBody=json.dumps(body))
            config=ReplayConfig(queue_url=url,function_arn='arn:aws:lambda:us-east-1:123456789012:function:collector',
                                region='us-east-1',max_messages=1)
            queue_reports.append(receive_and_replay(config,sqs,LocalLambda(),delete_success=True))
        detector.process(normalize(late)) # Explicit replacement of managed Streams transport.
        collision=copy.deepcopy(late);collision['detail']['eventName']='OtherAction'
        conflict=collector.collect(collision)
        snapshot=make_snapshot(before,coverage_start='2026-01-01T00:00:00Z',coverage_end='2026-01-02T00:00:00Z',
            source='synthetic-fixture',completeness_evidence='All outputs of the bounded 120-event generator, except the identified late event.',
            session_boundaries_verified=True)
        # Local CLI inputs: copy only existing realtime baseline, not corrections.
        for obj in s3.list_objects_v2(Bucket=bucket).get('Contents',[]):
            key=obj['Key']
            if key.startswith('results/realtime/') and '/reanalysis/' not in key:
                dest=output/'result-store'/key;dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(s3.get_object(Bucket=bucket,Key=key)['Body'].read())
        (output/'snapshot.json').write_text(json.dumps(snapshot,indent=2))
        (output/'late-events.json').write_text(json.dumps([late],indent=2))
        plan=plan_reanalysis(snapshot,[late])
        result=execute_reanalysis(plan,s3,bucket,bundle)
        # Actual chronological input windows with the same fixed model are the reference.
        from pipeline.ueba.events import windows
        reference={seq[-1]['eventID']:(seq,initial) for seq,initial in windows([normalize(e) for e in events])}
        for key in result['resultKeys']:
            row=get_json(s3,bucket,key);seq,initial=reference[row['eventID']]
            assert abs(row['result']['risk']-bundle.predict(seq,initial)['risk'])<1e-7
        from app.main import app
        from app.db.database import SessionLocal
        from app.models.result_source import ResultSource
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            r=client.post('/api/v1/users/register',json=dict(email='recovery@example.com',password='recovery-demo-only-47'));r.raise_for_status()
            uid=r.json()['id']
            login=client.post('/api/v1/users/login',data=dict(username='recovery@example.com',password='recovery-demo-only-47'));login.raise_for_status()
            headers={'Authorization':'Bearer '+login.json()['access_token']}
            r=client.post(f'/api/v1/credentials/{uid}/store',headers=headers,json=dict(name='demo',region='us-east-1',
                access_key_id='AKIAFAKEDEMOONLY',secret_access_key='fake-local-demo-only'));r.raise_for_status()
            with SessionLocal() as db:
                db.add(ResultSource(user_id=uid,credential_name='demo',bucket=bucket,
                    prefix=f"results/realtime/{digest(before[0]['userId'])}/",principal=before[0]['userId']));db.commit()
            sync=client.post(f'/api/v1/results/{uid}/import-s3',headers=headers,json=dict(credential_name='demo',max_files=1000));sync.raise_for_status()
            listed=client.get(f'/api/v1/ueba-results/{uid}?limit=1000',headers=headers);listed.raise_for_status()
            report=dict(mode='moto_local_only',synthetic_not_accuracy_evaluation=True,managed_retries_measured=False,
                input_events=len(events),training=training,replay_outcomes=[r['status'] for r in receipts],
                handler_timestamp_recorded='handlerEnteredAt' in receipts[0],deleted=sum(b['deleted'] for r in queue_reports for b in r['batches']),
                collision=conflict['status'],corrected_results=len(result['resultKeys']),
                chronological_reference_matches=True,notifications_published=result['notificationsPublished'],
                sync=sync.json(),queried=len(listed.json()),
                reanalysis_rows=sum(r['analysis_kind']=='reanalysis' for r in listed.json()))
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        (output/'queue-reports.json').write_text(json.dumps(queue_reports,indent=2)+'\n')
        print(json.dumps(dict(output=str(output),**report),indent=2))
        return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default=str(ROOT/'.demo/recovery'/str(uuid4())))
    args=p.parse_args();run(args.output)
