import copy,json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from botocore.exceptions import ClientError
from conftest import cloud_event
from pipeline.ueba.events import Collector,normalize,content_hash,HASH_POLICY,parse_time


def test_metadata_changes_and_json_order_are_not_content_collision(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');a=cloud_event()
    assert c.collect(a)['status']=='stored'
    b=json.loads(json.dumps(a,sort_keys=True));b.update(id='new-eventbridge-id',time='2026-02-01T00:00:00Z',resources=[])
    b['detail']['eventTime']='2026-01-01T09:00:00+09:00'
    assert content_hash(a)==content_hash(b)
    assert c.collect(b)['status']=='duplicate'


def test_changed_content_is_archived_and_original_preserved(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');a=cloud_event()
    c.collect(a);b=copy.deepcopy(a);b['detail']['eventName']='DeleteBucket'
    r=c.collect(b);assert r['status']=='conflict'
    saved=json.loads(s.get_object(Bucket='failure-archive',Key=r['failureKey'])['Body'].read())
    assert saved['original']==b and saved['reason']=='content_hash_mismatch'
    assert saved['storedHash']!=saved['incomingHash']
    rows=[row for row in t.scan()['Items'] if 'eventID' in row]
    assert len(rows)==1 and rows[0]['eventName']==a['detail']['eventName']


def test_concurrent_different_content_one_winner(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');a=cloud_event();b=copy.deepcopy(a);b['detail']['eventName']='OtherAction'
    with ThreadPoolExecutor(max_workers=2) as pool: outcomes=list(pool.map(c.collect,[a,b]))
    assert sorted(r['status'] for r in outcomes)==['conflict','stored']


def test_legacy_marker_requires_review_not_duplicate(aws):
    t,s=aws;e=cloud_event();t.put_item(Item={'pk':'EVENT#123456789012#evt-00000','sk':'DEDUP'})
    r=Collector(t,s,'failure-archive').collect(e)
    assert r['status']=='conflict' and r['reason']=='legacy_or_unknown_hash_policy'
    assert not any('eventID' in r for r in t.scan()['Items'])


def test_conflict_archive_failure_and_marker_read_failure_propagate(aws,monkeypatch):
    t,s=aws;c=Collector(t,s,'failure-archive');a=cloud_event();c.collect(a)
    b=copy.deepcopy(a);b['detail']['eventName']='Other'
    monkeypatch.setattr(s,'put_object',Mock(side_effect=RuntimeError('down')))
    with pytest.raises(RuntimeError): c.collect(b)
    monkeypatch.setattr(t,'get_item',Mock(side_effect=RuntimeError('read down')))
    with pytest.raises(RuntimeError): c.collect(a)


def test_ttl_race_marker_absent_is_not_acknowledged(aws,monkeypatch):
    t,s=aws;c=Collector(t,s,'failure-archive');e=cloud_event();c.collect(e)
    monkeypatch.setattr(t,'get_item',Mock(return_value={}))
    with pytest.raises(ClientError): c.collect(e)


def test_behavior_condition_failure_leaves_no_marker(aws):
    t,s=aws;e=cloud_event();t.put_item(Item=normalize(e))
    with pytest.raises(ClientError): Collector(t,s,'failure-archive').collect(e)
    assert 'Item' not in t.get_item(Key={'pk':'EVENT#123456789012#evt-00000','sk':'DEDUP'},ConsistentRead=True)


def test_handler_entry_is_a_real_handler_timestamp(aws,monkeypatch):
    import importlib.util
    from pathlib import Path
    t,s=aws
    path=Path(__file__).resolve().parents[1]/'pipeline/UEBA/modules/ct-ingest/collector/event_collector.py'
    spec=importlib.util.spec_from_file_location('collector_handler',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setenv('USER_EVENT_TABLE','events');monkeypatch.setenv('FAILURE_BUCKET','failure-archive')
    r=m.handler(cloud_event(),None)
    row=next(row for row in t.scan()['Items'] if 'eventID' in row)
    assert parse_time(r['handlerEnteredAt'])<=parse_time(row['writeRequestedAt'])<=parse_time(r['storedAt'])

def test_expired_marker_and_missing_behavior_do_not_acknowledge_duplicate(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');e=cloud_event();c.collect(e)
    row=normalize(e);t.delete_item(Key={'pk':row['pk'],'sk':row['sk']})
    assert c.collect(e)['reason']=='behavior_record_missing_or_inconsistent'
    t.update_item(Key={'pk':'EVENT#123456789012#evt-00000','sk':'DEDUP'},
                  UpdateExpression='SET expiresAt=:old',ExpressionAttributeValues={':old':1})
    assert c.collect(e)['reason']=='marker_retention_expired_or_unknown'

def test_same_event_id_in_different_accounts_is_independent(aws):
    t,s=aws;c=Collector(t,s,'failure-archive');a=cloud_event();b=copy.deepcopy(a)
    b['detail']['userIdentity']['accountId']='999999999999'
    b['detail']['userIdentity']['arn']='arn:aws:iam::999999999999:user/ALICE'
    assert c.collect(a)['status']=='stored' and c.collect(b)['status']=='stored'
    rows=[r for r in t.scan()['Items'] if 'eventID' in r]
    assert len(rows)==2 and len({r['pk'] for r in rows})==2
