"""Review retained failures; live replay requires explicit non-secret target configuration.

No AWS clients or requests are created by the default archive/dry-run path.
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.ueba.events import normalize,content_hash,HASH_POLICY


def unwrap(obj,_depth=0):
    if _depth>8: raise ValueError('envelope_depth_limit')
    if isinstance(obj,str):
        if len(obj)>1024*1024: raise ValueError('message_size_limit')
        return unwrap(json.loads(obj),_depth+1)
    if not isinstance(obj,dict): raise ValueError('object_required')
    if 'Messages' in obj:
        if not isinstance(obj['Messages'],list) or len(obj['Messages'])>100:
            raise ValueError('message_batch_limit')
        rows=[]
        for message in obj['Messages']:
            rows.extend(unwrap(message,_depth+1))
            if len(rows)>100: raise ValueError('message_batch_limit')
        return rows
    if 'Body' in obj: return unwrap(obj['Body'],_depth+1)
    if 'requestPayload' in obj: return unwrap(obj['requestPayload'],_depth+1)
    if 'original' in obj: return [obj['original']]
    if 'Records' in obj and isinstance(obj['Records'],list) and any('dynamodb' in r for r in obj['Records']):
        return [obj] # Offline extraction only. Collector replay rejects Streams payloads.
    if isinstance(obj.get('detail'),dict): return [obj]
    raise ValueError('unsupported_failure_envelope_or_payload_missing')


@dataclass(frozen=True)
class ReplayConfig:
    queue_url: str
    function_arn: str
    region: str
    max_messages: int = 10
    max_seconds: int = 300
    visibility_seconds: int = 900
    invoke_read_timeout: int = 65
    max_receive_count: int = 5

    def __post_init__(self):
        target=re.fullmatch(r'arn:aws:lambda:([a-z0-9-]+):(\d{12}):function:([A-Za-z0-9_-]+)(?::[A-Za-z0-9_-]+)?',self.function_arn)
        queue=re.fullmatch(r'https://sqs\.([a-z0-9-]+)\.amazonaws\.com/(\d{12})/[A-Za-z0-9_-]+(?:\.fifo)?',self.queue_url)
        if not target or not queue or target[1]!=self.region or queue[1]!=self.region or target[2]!=queue[2]:
            raise ValueError('explicit_same_account_region_targets_required')
        if not 1<=self.max_messages<=100 or not 1<=self.max_seconds<=3600 or not 1<=self.invoke_read_timeout<=900:
            raise ValueError('replay_limit_invalid')
        # One receive obtains <=10 messages. Cover the entire serial batch plus margin.
        minimum=min(10,self.max_messages)*(self.invoke_read_timeout+5)+30
        if not minimum<=self.visibility_seconds<=43200 or not 1<=self.max_receive_count<=20:
            raise ValueError('visibility_or_receive_limit_invalid')


def replay_messages(messages,config,*,execute=False,delete_success=False,sqs=None,lambda_client=None,clock=monotonic):
    if len(messages)>config.max_messages: raise ValueError('message_batch_limit')
    if delete_success and not execute: raise ValueError('deletion_requires_execute')
    if execute and (sqs is None or lambda_client is None): raise ValueError('clients_required')
    deadline=clock()+config.max_seconds
    report=dict(executed=execute,messages=[],deleted=0)
    deletable=[]
    for index,message in enumerate(messages):
        result=dict(message_id=message.get('MessageId',str(index)),status='not_processed',deleted=False)
        report['messages'].append(result)
        try:
            events=unwrap(message)
            if len(events)!=1: raise ValueError('one_collector_event_per_message_required')
            normalize(events[0]) # Reject malformed input before invoking.
            expected_hash=content_hash(events[0])
            result['eventID']=events[0]['detail']['eventID'] if isinstance(events[0],dict) else None
            if not execute:
                result['status']='dry_run'; continue
            if int(message.get('Attributes',{}).get('ApproximateReceiveCount','1'))>config.max_receive_count:
                result['status']='receive_limit_requires_review'; continue
            if clock()+config.invoke_read_timeout+5>deadline:
                result['status']='time_budget_exhausted'; continue
            handle=message['ReceiptHandle']
            # Renew immediately before invocation; standard SQS still permits duplicates.
            sqs.change_message_visibility(QueueUrl=config.queue_url,ReceiptHandle=handle,
                                          VisibilityTimeout=config.visibility_seconds)
            response=lambda_client.invoke(FunctionName=config.function_arn,InvocationType='RequestResponse',
                                          Payload=json.dumps(events[0]).encode())
            if response.get('StatusCode')!=200 or response.get('FunctionError'):
                result['status']='lambda_execution_failed'; continue
            body=response['Payload'].read(1024*1024+1)
            if len(body)>1024*1024: raise ValueError('response_size_limit')
            outcome=json.loads(body)
            # HTTP success alone is insufficient; invalid/conflict are review cases.
            if (not isinstance(outcome,dict) or outcome.get('status') not in ('stored','duplicate')
                or outcome.get('eventID')!=result['eventID'] or outcome.get('hashPolicy')!=HASH_POLICY
                or outcome.get('contentHash')!=expected_hash):
                result['status']='collector_outcome_requires_review'; continue
            result['status']=outcome['status']
            if delete_success: deletable.append((index,handle,result))
        except (ValueError,KeyError,TypeError,AttributeError):
            result['status']='malformed_or_incomplete_message'
        except Exception:
            # Includes timeout after a possible successful invocation: keep the message.
            result['status']='aws_operation_failed'
    for start in range(0,len(deletable),10):
        batch=deletable[start:start+10]
        entries=[dict(Id=str(i),ReceiptHandle=h) for i,h,_ in batch]
        try:
            response=sqs.delete_message_batch(QueueUrl=config.queue_url,Entries=entries)
            succeeded={r['Id'] for r in response.get('Successful',[])}
            failed={r['Id'] for r in response.get('Failed',[])}
            for i,_,result in batch:
                result['deleted']=str(i) in succeeded and str(i) not in failed
                result['delete_status']='deleted' if result['deleted'] else 'delete_failed_or_unconfirmed'
                report['deleted']+=int(result['deleted'])
        except Exception:
            for _,_,result in batch: result['delete_status']='delete_failed_or_unconfirmed'
    return report


def receive_and_replay(config,sqs,lambda_client,*,delete_success=False,clock=monotonic):
    """Bounded worker invocation, not a permanently polling service."""
    started=clock(); remaining=config.max_messages; reports=[]; stopped='message_limit'
    while remaining>0:
        if clock()+config.invoke_read_timeout+5>=started+config.max_seconds:
            stopped='time_budget';break
        response=sqs.receive_message(QueueUrl=config.queue_url,MaxNumberOfMessages=min(10,remaining),
            WaitTimeSeconds=0,VisibilityTimeout=config.visibility_seconds,
            MessageSystemAttributeNames=['ApproximateReceiveCount'])
        messages=response.get('Messages',[])
        if not messages:
            stopped='empty';break
        if len(messages)>remaining: raise ValueError('unexpected_receive_count')
        from dataclasses import replace
        budget=max(1,int(config.max_seconds-(clock()-started)))
        current=replace(config,max_seconds=budget)
        reports.append(replay_messages(messages,current,execute=True,delete_success=delete_success,
                                       sqs=sqs,lambda_client=lambda_client,clock=clock))
        remaining-=len(messages)
    return dict(received=config.max_messages-remaining,batches=reports,
                stopped=stopped,elapsed_seconds=clock()-started)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',nargs='?')
    parser.add_argument('--output')
    parser.add_argument('--config',help='Operator-controlled JSON target binding; never read targets from messages')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--receive',action='store_true')
    parser.add_argument('--delete-success',action='store_true')
    args=parser.parse_args()
    if not args.execute:
        if args.receive or args.delete_success: parser.error('receive/deletion require --execute')
        if not args.archive or not args.output: parser.error('dry-run requires archive and --output')
        path=Path(args.archive)
        if path.stat().st_size>20*1024*1024: parser.error('archive_size_limit')
        rows=unwrap(json.loads(path.read_text()))
        invalid=0
        for row in rows:
            try: normalize(row)
            except (ValueError,KeyError,TypeError,AttributeError): invalid+=1
        with open(args.output,'x') as f:
            for row in rows: f.write(json.dumps(row)+'\n')
        print(json.dumps(dict(status='extracted_for_review',events=len(rows),invalid_for_collector=invalid,aws_requests=0)))
        if invalid: raise SystemExit(2)
        return
    if not args.config or not args.receive or args.archive:
        parser.error('live execution requires --config and --receive; no arbitrary archive invocation')
    config=ReplayConfig(**json.loads(Path(args.config).read_text()))
    import boto3
    from botocore.config import Config
    # Explicit single attempt: a timed-out invocation might already have stored data.
    sdk=Config(connect_timeout=5,read_timeout=config.invoke_read_timeout,retries={'total_max_attempts':1})
    result=receive_and_replay(config,boto3.client('sqs',region_name=config.region,config=sdk),
        boto3.client('lambda',region_name=config.region,config=sdk),delete_success=args.delete_success)
    print(json.dumps(result))
    if result['stopped']=='time_budget' or any(r['status'] not in ('stored','duplicate') or r.get('delete_status')=='delete_failed_or_unconfirmed'
           for batch in result['batches'] for r in batch['messages']): raise SystemExit(2)

if __name__=='__main__': main()
