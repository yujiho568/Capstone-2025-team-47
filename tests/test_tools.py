from tools.latency import summarize
from tools.replay import unwrap

def test_latency_measured_counts_missing_duplicates():
    events=[dict(eventID='a',timestamp='2026-01-01T00:00:00Z'),dict(eventID='b',timestamp='2026-01-01T00:00:00Z')]
    r=[dict(eventID='a',storedAt='2026-01-01T00:00:02Z'),dict(eventID='a',storedAt='2026-01-01T00:00:03Z')]
    out=summarize(events,r)
    assert out['matched']==1 and out['missing']==1 and out['storage_duplicates']==1
    assert out['statistics']['mean_seconds']==2
    assert out['source_precision']=='seconds'

def test_replay_retains_original():
    event={'detail':{'eventID':'a'}}
    assert unwrap({'requestPayload':event})==[event]
    assert unwrap({'original':event,'reason':'KeyError'})==[event]

def test_current_clock_latency_records_actual_stages(tmp_path):
    from tools.measure_local_latency import measure
    from pipeline.ueba.events import parse_time
    path, report=measure(count=3,repetitions=1,output=tmp_path/'measurement')
    assert report['completed_events']==3 and report['completed_repetitions']==1
    assert report['aws_cloudtrail_measured'] is False
    r=report['repetitions'][0]
    assert r['matched']==3 and r['missing']==0 and r['storage_duplicates']==0
    assert r['duplicate_replay_status']=='duplicate'
    s=r['sample']
    assert parse_time(s['eventTime'])<=parse_time(s['collectorReceivedAt'])<=parse_time(s['writeRequestedAt'])<=parse_time(s['storedAt'])
    assert (path/'run-1-receipts.jsonl').exists()

def test_stage_timings_do_not_invent_missing_cloudwatch_or_handler_samples():
    events=[{'eventID':'a','timestamp':'2026-01-01T00:00:00Z'}]
    receipts=[dict(eventID='a',collectorReceivedAt='2026-01-01T00:00:01Z',
                   writeRequestedAt='2026-01-01T00:00:02Z',storedAt='2026-01-01T00:00:03Z')]
    r=summarize(events,receipts)
    assert r['stages']['write_request_to_ack']['statistics']['mean_seconds']==1
    assert r['stages']['event_to_handler']['samples']==0
    assert r['stages']['event_to_cloudwatch_ingestion']['statistics'] is None
    receipts[0].update(handlerEnteredAt='2026-01-01T00:00:01Z',
                       ingestionTime='2026-01-01T00:00:04Z',readAt='2026-01-01T00:00:02Z')
    r=summarize(events,receipts)
    assert r['stages']['event_to_handler']['samples']==1
    assert r['stages']['cloudwatch_ingestion_to_read']['negative_count']==1
