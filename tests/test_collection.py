import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from botocore.exceptions import ClientError
from pipeline.ueba.events import Collector,normalize
from conftest import cloud_event

def test_normal_duplicate_collision_and_ttl(aws):
    table,s3=aws;c=Collector(table,s3,'failure-archive')
    e=cloud_event(0)
    assert c.collect(e)['status']=='stored'
    assert c.collect(e)['status']=='duplicate' # response lost after success
    e2=cloud_event(1,timestamp=e['detail']['eventTime'])
    assert c.collect(e2)['status']=='stored'
    rows=[r for r in table.scan()['Items'] if 'eventID' in r]
    assert len(rows)==2
    assert all(int(r['expiresAt'])>0 and r['writeRequestedAt']!=r['timestamp'] for r in rows)
    assert all(not isinstance(r['expiresAt'],str) for r in rows)

def test_concurrent_duplicate(aws):
    table,s3=aws;c=Collector(table,s3,'failure-archive')
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(c.collect,[cloud_event(0)]*8))
    assert sum(r['status']=='stored' for r in results)==1
    assert sum(r['status']=='duplicate' for r in results)==7
    assert len([r for r in table.scan()['Items'] if 'eventID' in r])==1

def test_invalid_archive_and_invalid_json(aws):
    t,s=aws;c=Collector(t,s,'failure-archive')
    for event in ({'detail':{}},'{bad json',None):
        out=c.collect(event)
        assert out['status']=='invalid'
        archive=json.loads(s.get_object(Bucket='failure-archive',Key=out['failureKey'])['Body'].read())
        assert archive['original']==event and archive['reason']

def test_storage_failure_propagates(aws):
    _,s=aws;t=Mock();t.name='test'
    err=ClientError({'Error':{'Code':'ProvisionedThroughputExceededException'}},'TransactWriteItems')
    t.meta.client.transact_write_items.side_effect=err
    with pytest.raises(ClientError): Collector(t,s,'failure-archive').collect(cloud_event())
    s=Mock();s.put_object.side_effect=RuntimeError('archive down')
    with pytest.raises(RuntimeError): Collector(t,s,'failure-archive').collect({})

def test_non_duplicate_transaction_failure_not_hidden(aws):
    _,s=aws;t=Mock();t.name='test'
    t.meta.client.transact_write_items.side_effect=ClientError({'Error':{'Code':'TransactionCanceledException'},
        'CancellationReasons':[{'Code':'None'},{'Code':'ConditionalCheckFailed'}]},'TransactWriteItems')
    with pytest.raises(ClientError): Collector(t,s,'failure-archive').collect(cloud_event())

def test_dedup_eventid_even_changed_timestamp_identity(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');e=cloud_event()
    c.collect(e);e['detail']['eventTime']='2026-02-01T00:00:00Z';e['detail']['userIdentity']['principalId']='OTHER'
    assert c.collect(e)['status']=='duplicate'

def test_completion_receipt_is_after_success(aws):
    from pipeline.ueba.events import parse_time
    t,s=aws
    receipt=Collector(t,s,'failure-archive').collect(cloud_event())
    row=next(r for r in t.scan()['Items'] if 'eventID' in r)
    assert 'storedAt' not in row
    assert parse_time(receipt['storedAt'])>=parse_time(row['writeRequestedAt'])
