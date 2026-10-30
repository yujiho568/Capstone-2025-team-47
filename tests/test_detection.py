import json
from unittest.mock import Mock
import pytest
from boto3.dynamodb.types import TypeSerializer
from pipeline.ueba.events import normalize,sessions,windows,Collector,history,parse_time
from pipeline.ueba.models import Bundle,ModelUnavailable,train
from pipeline.ueba.detection import Detector
from conftest import cloud_event

def test_session_boundaries_ties_and_short():
    rows=[normalize(cloud_event(i)) for i in range(21)]
    rows+= [normalize(cloud_event(50,user='BOB'))]
    rows+= [normalize(cloud_event(51,timestamp='2026-01-01T00:33:20Z'))] # exact 30m after 00:03:20
    groups=sessions(list(reversed(rows)))
    assert sorted(map(len,groups))==[1,1,21]
    samples=list(windows(rows))
    assert [flag for _,flag in samples]==[True,False]
    assert all(len({r['userId'] for r in seq})==1 for seq,_ in samples)
    assert list(windows(rows[:19]))==[]
    a=normalize(cloud_event(2,timestamp='2026-01-01T00:00:00Z'))
    b=normalize(cloud_event(1,timestamp='2026-01-01T00:00:00Z'))
    assert sessions([a,b])[0]==[b,a]

def test_real_models_missing_version_and_checksum(model_dir,tmp_path):
    model=Bundle(model_dir,'v1')
    seq=[normalize(cloud_event(i)) for i in range(20)]
    for initial in (True,False):
        pred=model.predict(seq,initial)
        assert 0<=pred['risk']<=100
    with pytest.raises(ModelUnavailable): Bundle(model_dir,'missing')
    assert train(seq,tmp_path,'not-created')['status']=='skipped'
    import shutil
    shutil.copytree(model_dir/'v1',tmp_path/'v2')
    with pytest.raises(ModelUnavailable): Bundle(tmp_path,'v2')
    (tmp_path/'v2'/'manifest.json').write_text('{}')
    with pytest.raises(ModelUnavailable): Bundle(tmp_path,'v2')

def test_stable_results_collision_and_version(aws,model_dir):
    table,s3=aws;c=Collector(table,s3,'failure-archive')
    for i in range(22): c.collect(cloud_event(i))
    bundle=Bundle(model_dir,'v1');d=Detector(table,s3,'ueba-results',bundle)
    a=normalize(cloud_event(20));out=d.process(a)
    again=d.process(a)
    assert out['key']==again['key'] and out['payload']==again['payload']
    # Same timestamp, distinct event ID yields distinct immutable result.
    e=cloud_event(23,timestamp=cloud_event(20)['detail']['eventTime']);c.collect(e)
    other=d.process(normalize(e));assert other['key']!=out['key']
    bundle.version='v2'
    assert d.process(a)['key']!=out['key']

def test_streams_types_batch_checkpoint():
    d=Detector(None,None,None,None);d.process=Mock(side_effect=[RuntimeError('bad')])
    ser=TypeSerializer();row={k:ser.serialize(v) for k,v in normalize(cloud_event()).items()}
    record=lambda n,kind='INSERT',img=row:dict(eventName=kind,dynamodb=dict(NewImage=img,SequenceNumber=str(n)))
    out=d.batch({'Records':[record(1,'REMOVE'),record(2,'MODIFY'),record(3,img={'sk':{'S':'DEDUP'}}),record(4),record(5)]})
    assert out=={'batchItemFailures':[{'itemIdentifier':'4'}]}
    assert d.process.call_count==1

def test_result_saved_before_notification_failure_and_retry(aws,model_dir):
    t,s=aws;c=Collector(t,s,'failure-archive')
    for i in range(20): c.collect(cloud_event(i))
    bundle=Bundle(model_dir,'v1')
    # Force anomaly only to test delivery fault, not to claim model accuracy.
    bundle.predict=Mock(return_value={'engine':'ocsvm','is_anomaly':True,'score':-1.,'risk':99.})
    events=Mock();events.put_events.return_value={'FailedEntryCount':1}
    d=Detector(t,s,'ueba-results',bundle,events,alert_max_age_seconds=60,
               now=lambda:parse_time(cloud_event(19)['detail']['eventTime']))
    with pytest.raises(RuntimeError): d.process(normalize(cloud_event(19)))
    assert s.list_objects_v2(Bucket='ueba-results')['KeyCount']==1
    events.put_events.return_value={'FailedEntryCount':0}
    d.process(normalize(cloud_event(19)))
    assert bundle.predict.call_count==1 and events.put_events.call_count==2

def test_lambda_model_version_switch_and_manifest_mismatch(aws,model_dir,tmp_path,monkeypatch):
    import shutil
    import pipeline.realtime_container.lambda_realtime_handler as handler
    t,s3=aws
    monkeypatch.setattr(handler,'_bundle',None)
    for version in ('v1','v2'):
        dest=tmp_path/version;shutil.copytree(model_dir/'v1',dest)
        manifest=json.loads((dest/'manifest.json').read_text());manifest['version']=version
        (dest/'manifest.json').write_text(json.dumps(manifest))
        for path in dest.iterdir(): s3.put_object(Bucket='ueba-results',Key=f'models/bundles/{version}/{path.name}',Body=path.read_bytes())
    first=handler.load_bundle(s3,'ueba-results','v1')
    assert handler.load_bundle(s3,'ueba-results','v1') is first
    assert handler.load_bundle(s3,'ueba-results','v2').version=='v2'
    with pytest.raises(ModelUnavailable): handler.load_bundle(s3,'ueba-results','missing')

def test_ttl_delete_does_not_require_model(monkeypatch):
    import pipeline.realtime_container.lambda_realtime_handler as handler
    loader=Mock(side_effect=AssertionError('must not load model for TTL deletion'))
    monkeypatch.setattr(handler,'load_bundle',loader)
    assert handler.lambda_handler({'Records':[{'eventName':'REMOVE','dynamodb':{}}]},None)=={'batchItemFailures':[]}
    loader.assert_not_called()

def test_batch_preserves_completed_prefix_and_reports_first_failed_record():
    d=Detector(None,None,None,None);d.process=Mock(side_effect=[{'status':'complete'},RuntimeError('bad')])
    ser=TypeSerializer();image={k:ser.serialize(v) for k,v in normalize(cloud_event()).items()}
    records=[dict(eventName='INSERT',dynamodb=dict(NewImage=image,SequenceNumber=str(i))) for i in (10,11,12)]
    assert d.batch({'Records':records})=={'batchItemFailures':[{'itemIdentifier':'11'}]}
    assert d.process.call_count==2

def test_recent_history_is_bounded_without_changing_initial_flag(aws):
    t,s=aws;c=Collector(t,s,'failure-archive')
    for i in range(80): c.collect(cloud_event(i))
    rows=history(t,normalize(cloud_event(79)))
    assert len(rows)==41
    seq,initial=list(windows(rows))[-1]
    assert len(seq)==20 and not initial and seq[-1]['eventID']=='evt-00079'

def test_historical_stream_event_cannot_emit_current_alerts(aws,model_dir):
    from datetime import timedelta
    from pipeline.ueba.events import parse_time
    t,s=aws;c=Collector(t,s,'failure-archive')
    for i in range(20): c.collect(cloud_event(i))
    bundle=Bundle(model_dir,'v1')
    bundle.predict=Mock(return_value={'engine':'ocsvm','is_anomaly':True,'score':-1.,'risk':99.})
    events=Mock()
    with pytest.raises(ValueError): Detector(t,s,'ueba-results',bundle,events)
    d=Detector(t,s,'ueba-results',bundle,events,alert_max_age_seconds=60,
               now=lambda:parse_time(cloud_event(19)['detail']['eventTime'])+timedelta(hours=3))
    result=d.process(normalize(cloud_event(19)))
    assert result['notificationStatus']=='historical_or_future_event_suppressed'
    events.put_events.assert_not_called()
