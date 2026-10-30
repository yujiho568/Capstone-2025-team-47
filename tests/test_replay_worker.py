import io,json
from unittest.mock import Mock
import pytest
import boto3
from conftest import cloud_event
from pipeline.ueba.events import Collector,content_hash,HASH_POLICY
from tools.replay import unwrap,ReplayConfig,replay_messages,receive_and_replay

URL='https://sqs.us-east-1.amazonaws.com/123456789012/recovery'
ARN='arn:aws:lambda:us-east-1:123456789012:function:collector'

def config(**kw): return ReplayConfig(queue_url=URL,function_arn=ARN,region='us-east-1',**kw)

def message(i=0,execution=False):
    event=cloud_event(i)
    return dict(MessageId=str(i),ReceiptHandle=f'handle-{i}',Body=json.dumps({'requestPayload':event,'responseContext':{'functionError':'Unhandled'}} if execution else event))

def response(status='stored',eid='evt-00000',**extra):
    return dict(StatusCode=200,Payload=io.BytesIO(json.dumps(dict(status=status,eventID=eid,hashPolicy=HASH_POLICY,
        contentHash=content_hash(cloud_event(int(eid.split('-')[1]))) if eid.startswith('evt-') else 'bad')).encode()),**extra)


def test_two_envelopes_arrays_and_malformed():
    assert unwrap({'Messages':[message(),message(1,True)]})==[cloud_event(),cloud_event(1)]
    for body in ('{bad',{},None,{'requestContext':{}}):
        with pytest.raises((ValueError,TypeError)): unwrap(body)


def test_dry_run_never_invokes_or_deletes():
    sqs=Mock();client=Mock()
    r=replay_messages([message(),message(1,True)],config(),sqs=sqs,lambda_client=client)
    assert [m['status'] for m in r['messages']]==['dry_run','dry_run']
    sqs.assert_not_called();client.assert_not_called()
    assert sqs.mock_calls==[] and client.mock_calls==[]
    with pytest.raises(ValueError): replay_messages([message()],config(),delete_success=True)

@pytest.mark.parametrize('reply',[response(FunctionError='Unhandled'),response('invalid'),response('conflict'),response('stored',eid='different')])
def test_http_success_is_not_always_recovery_success(reply):
    sqs=Mock();client=Mock();client.invoke.return_value=reply
    r=replay_messages([message()],config(),execute=True,delete_success=True,sqs=sqs,lambda_client=client)
    assert r['deleted']==0 and r['messages'][0]['status'] not in ('stored','duplicate')
    sqs.delete_message_batch.assert_not_called()


def test_partial_delete_failure_is_reported():
    sqs=Mock();client=Mock();client.invoke.side_effect=[response(),response('duplicate','evt-00001')]
    sqs.delete_message_batch.return_value={'Successful':[{'Id':'0'}],'Failed':[{'Id':'1','Code':'InternalError'}]}
    r=replay_messages([message(),message(1,True)],config(),execute=True,delete_success=True,sqs=sqs,lambda_client=client)
    assert r['deleted']==1 and r['messages'][1]['delete_status']=='delete_failed_or_unconfirmed'


def test_timeout_receive_limit_budget_and_malformed_keep_messages():
    sqs=Mock();client=Mock();client.invoke.side_effect=TimeoutError()
    m=message(1);m['Attributes']={'ApproximateReceiveCount':'6'}
    r=replay_messages([message(),m,{'Body':'{bad'}],config(),execute=True,delete_success=True,sqs=sqs,lambda_client=client)
    assert r['deleted']==0
    assert [x['status'] for x in r['messages']]==['aws_operation_failed','receive_limit_requires_review','malformed_or_incomplete_message']
    sqs.delete_message_batch.assert_not_called()
    client.reset_mock();replay_messages([message()],config(max_seconds=1),execute=True,sqs=sqs,lambda_client=client)
    client.invoke.assert_not_called()


def test_moto_sqs_worker_response_loss_and_duplicate_delivery(aws):
    table,s3=aws;collector=Collector(table,s3,'failure-archive')
    sqs=boto3.client('sqs');url=sqs.create_queue(QueueName='recovery')['QueueUrl']
    cfg=ReplayConfig(queue_url=url,function_arn=ARN,region='us-east-1',max_messages=2)
    sqs.send_message(QueueUrl=url,MessageBody=json.dumps(cloud_event()))
    class Invoke:
        lose=True
        def invoke(self,**kw):
            result=collector.collect(json.loads(kw['Payload']))
            if self.lose:
                self.lose=False;raise TimeoutError('response lost after commit')
            return dict(StatusCode=200,Payload=io.BytesIO(json.dumps(result).encode()))
    client=Invoke();r=receive_and_replay(cfg,sqs,client,delete_success=True)
    assert r['batches'][0]['deleted']==0
    # Simulate visibility expiry without waiting. Original message was never deleted.
    messages=sqs.receive_message(QueueUrl=url,VisibilityTimeout=0).get('Messages',[])
    assert messages==[] # still invisible
    # Deliberately simulate a second standard-queue delivery/worker of the same event.
    sqs.send_message(QueueUrl=url,MessageBody=json.dumps({'requestPayload':cloud_event()}))
    r=receive_and_replay(cfg,sqs,client,delete_success=True)
    assert r['batches'][0]['messages'][0]['status']=='duplicate' and r['batches'][0]['deleted']==1
    assert len([x for x in table.scan()['Items'] if 'eventID' in x])==1


def test_target_binding_and_bounds():
    with pytest.raises(ValueError): ReplayConfig(queue_url=URL,function_arn=ARN.replace('123456789012','999999999999'),region='us-east-1')
    with pytest.raises(ValueError): config(visibility_seconds=1)
    with pytest.raises(ValueError): config(max_messages=101)

def test_old_collector_protocol_is_not_automatically_acknowledged():
    sqs=Mock();client=Mock()
    client.invoke.return_value=dict(StatusCode=200,Payload=io.BytesIO(b'{"status":"duplicate","eventID":"evt-00000"}'))
    r=replay_messages([message()],config(),execute=True,delete_success=True,sqs=sqs,lambda_client=client)
    assert r['deleted']==0 and r['messages'][0]['status']=='collector_outcome_requires_review'


def test_receive_worker_stops_without_requests_when_budget_is_too_short():
    sqs=Mock();client=Mock()
    r=receive_and_replay(config(max_seconds=1),sqs,client)
    assert r['received']==0 and r['stopped']=='time_budget'
    sqs.receive_message.assert_not_called();client.invoke.assert_not_called()


def test_cli_default_extracts_array_without_aws_clients(tmp_path,monkeypatch,capsys):
    from tools.replay import main
    import sys
    source=tmp_path/'messages.json';output=tmp_path/'review.jsonl'
    source.write_text(json.dumps({'Messages':[message(),message(1,True)]}))
    client=Mock(side_effect=AssertionError('no SDK clients allowed in dry run'))
    monkeypatch.setattr(boto3,'client',client)
    monkeypatch.setattr(sys,'argv',['replay.py',str(source),'--output',str(output)])
    main()
    assert len(output.read_text().splitlines())==2 and json.loads(capsys.readouterr().out)['aws_requests']==0
    client.assert_not_called()

def test_concurrent_workers_share_idempotent_collector(aws):
    from concurrent.futures import ThreadPoolExecutor
    table,s3=aws;collector=Collector(table,s3,'failure-archive');sqs=Mock()
    sqs.delete_message_batch.return_value={'Successful':[{'Id':'0'}]}
    class Invoke:
        def invoke(self,**kw):
            outcome=collector.collect(json.loads(kw['Payload']))
            return dict(StatusCode=200,Payload=io.BytesIO(json.dumps(outcome).encode()))
    def run(i):
        m=message();m['ReceiptHandle']=f'delivery-{i}'
        return replay_messages([m],config(),execute=True,delete_success=True,sqs=sqs,lambda_client=Invoke())
    with ThreadPoolExecutor(max_workers=2) as pool: reports=list(pool.map(run,[0,1]))
    assert sorted(r['messages'][0]['status'] for r in reports)==['duplicate','stored']
    assert sum(r['deleted'] for r in reports)==2
    assert len([x for x in table.scan()['Items'] if 'eventID' in x])==1
