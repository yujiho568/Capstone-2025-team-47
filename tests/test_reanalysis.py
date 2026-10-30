import copy,json
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from conftest import cloud_event
from pipeline.ueba.events import normalize,Collector,windows,digest
from pipeline.ueba.models import Bundle
from pipeline.ueba.detection import Detector,input_digest,realtime_key
from pipeline.ueba.reanalysis import make_snapshot,plan_reanalysis,execute_reanalysis,ReanalysisUnavailable,get_json,complete_manifest_key


def snapshot(rows):
    return make_snapshot(rows,coverage_start='2026-01-01T00:00:00Z',coverage_end='2026-01-02T00:00:00Z',
        source='synthetic-fixture',completeness_evidence='All generator outputs for the complete bounded synthetic sessions.',
        session_boundaries_verified=True)


def test_late_event_reanalysis_matches_chronological_actual_model(aws,model_dir):
    t,s=aws;collector=Collector(t,s,'failure-archive');bundle=Bundle(model_dir,'v1')
    detector=Detector(t,s,'ueba-results',bundle)
    events=[cloud_event(i) for i in range(60)];before=[]
    for i,event in enumerate(events):
        if i==25: continue
        collector.collect(event);before.append(normalize(event));detector.process(normalize(event))
    original={obj['Key']:s.get_object(Bucket='ueba-results',Key=obj['Key'])['Body'].read()
              for obj in s.list_objects_v2(Bucket='ueba-results')['Contents']}
    collector.collect(events[25]);detector.process(normalize(events[25]))
    snap=snapshot(before);plan=plan_reanalysis(snap,[events[25]])
    assert len(plan['affected'])==20
    result=execute_reanalysis(plan,s,'ueba-results',bundle)
    assert result['notificationsPublished']==0
    expected={seq[-1]['eventID']:(seq,initial) for seq,initial in windows([normalize(e) for e in events])}
    for key in result['resultKeys']:
        out=get_json(s,'ueba-results',key);seq,initial=expected[out['eventID']]
        assert out['inputEventIDs']==[r['eventID'] for r in seq]
        assert out['inputDigest']==input_digest(seq,initial)
        assert out['result']['risk']==pytest.approx(bundle.predict(seq,initial)['risk'],abs=1e-7)
        assert out['analysisKind']=='reanalysis' and out['modelVersion']=='v1'
    again=execute_reanalysis(plan,s,'ueba-results',bundle)
    assert result==again
    # TTL assigned to the incoming late copy must not create a new analysis identity.
    replanned=plan_reanalysis(snap,[events[25]],now=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert plan['afterDigest']==replanned['afterDigest']
    for key,body in original.items(): assert s.get_object(Bucket='ueba-results',Key=key)['Body'].read()==body


def test_late_event_merges_sessions_and_changes_initial_flags():
    events=[cloud_event(i) for i in range(30)]
    events += [cloud_event(i,timestamp=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=i*10+1900)).isoformat()) for i in range(30,70)]
    late=cloud_event(100,timestamp='2026-01-01T00:25:00Z')
    p=plan_reanalysis(snapshot([normalize(e) for e in events]),[late])
    changed={r['eventID']:r for r in p['affected']}
    assert 'evt-00049' in changed # 20th endpoint of old second session.
    assert changed['evt-00049']['initial'] is False
    assert changed['evt-00049']['beforeDigest'] is not None


def test_history_integrity_expiry_missing_coverage_and_bounds():
    rows=[normalize(cloud_event(i)) for i in range(30)];snap=snapshot(rows)
    bad=copy.deepcopy(snap);bad['sessionBoundariesVerified']=False
    with pytest.raises(ReanalysisUnavailable): plan_reanalysis(bad,[cloud_event(100)])
    bad=copy.deepcopy(snap);bad['events'].pop()
    with pytest.raises(ReanalysisUnavailable): plan_reanalysis(bad,[cloud_event(100)])
    expired=copy.deepcopy(rows);expired[0]['expiresAt']=1
    with pytest.raises(ReanalysisUnavailable,match='expired'): plan_reanalysis(snapshot(expired),[cloud_event(100)])
    with pytest.raises(ReanalysisUnavailable): plan_reanalysis(snap,[cloud_event(100)],max_events=10)
    late=cloud_event(100,timestamp='2026-01-01T00:02:35Z')
    with pytest.raises(ReanalysisUnavailable,match='affected'): plan_reanalysis(snap,[late],max_results=1)
    with pytest.raises(ReanalysisUnavailable): plan_reanalysis(snap,[cloud_event(100,user='OTHER')])


def test_partial_run_no_completion_and_no_alerts_then_resume(aws,model_dir):
    t,s=aws;bundle=Bundle(model_dir,'v1')
    rows=[normalize(cloud_event(i)) for i in range(40)]
    plan=plan_reanalysis(snapshot(rows),[cloud_event(100,timestamp='2026-01-01T00:04:05Z')])
    clock=Mock(side_effect=[0,0,5])
    with pytest.raises(ReanalysisUnavailable,match='time_budget'):
        execute_reanalysis(plan,s,'ueba-results',bundle,analysis_version='partial',max_seconds=1,clock=clock)
    assert get_json(s,'ueba-results',complete_manifest_key(rows[0]['userId'],'v1','partial')) is None
    complete=execute_reanalysis(plan,s,'ueba-results',bundle,analysis_version='partial')
    assert complete['status']=='complete' and complete['notificationsPublished']==0
    assert get_json(s,'ueba-results',complete['completeManifestKey'])['status']=='complete'
    other=plan_reanalysis(snapshot(rows),[cloud_event(101,timestamp='2026-01-01T00:04:15Z')])
    with pytest.raises(ReanalysisUnavailable,match='immutable'):
        execute_reanalysis(other,s,'ueba-results',bundle,analysis_version='partial')


def test_legacy_result_without_input_provenance_cannot_be_silently_corrected(aws,model_dir):
    t,s=aws;bundle=Bundle(model_dir,'v1');rows=[normalize(cloud_event(i)) for i in range(40)]
    plan=plan_reanalysis(snapshot(rows),[cloud_event(100,timestamp='2026-01-01T00:04:05Z')])
    target=next(r for r in plan['affected'] if r['beforeDigest'])
    s.put_object(Bucket='ueba-results',Key=realtime_key(target['sequence'][-1],'v1'),Body=json.dumps({'ok':True}))
    with pytest.raises(ReanalysisUnavailable,match='provenance'):
        execute_reanalysis(plan,s,'ueba-results',bundle)

def test_local_store_atomic_immutable_and_path_scope(tmp_path):
    from tools.reanalyze import LocalResults
    from pipeline.ueba.reanalysis import put_immutable
    store=LocalResults(tmp_path/'results')
    put_immutable(store,'local','safe/value.json',{'ok':True})
    put_immutable(store,'local','safe/value.json',{'ok':True})
    with pytest.raises(ReanalysisUnavailable): put_immutable(store,'local','safe/value.json',{'ok':False})
    with pytest.raises(ValueError): store.get_object(Bucket='local',Key='../../escape')

def test_short_history_is_not_published_as_a_normal_analysis(aws):
    rows=[normalize(cloud_event(i)) for i in range(18)]
    with pytest.raises(ReanalysisUnavailable,match='insufficient_history'):
        plan_reanalysis(snapshot(rows),[cloud_event(18)])
    plan=plan_reanalysis(snapshot([normalize(cloud_event(i)) for i in range(30)]),[cloud_event(0)])
    assert plan['status']=='no_change'
    store=Mock()
    out=execute_reanalysis(plan,store,'ueba-results',SimpleNamespace(version='v1'))
    assert out['status']=='no_change' and out['resultKeys']==[]
    store.assert_not_called();assert store.mock_calls==[]
