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
