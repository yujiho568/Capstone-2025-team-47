"""Offline eventID matching. Each --receipt path is a separately observed path/run."""
import argparse,json,math,statistics
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

def timestamp(s):
    d=datetime.fromisoformat(s.replace('Z','+00:00'))
    if not d.tzinfo: raise ValueError('timezone_required')
    return d

def stage_statistics(origins,stored_receipts):
    definitions={
        'event_to_handler':('eventTime','handlerEnteredAt'),
        'event_to_local_caller':('eventTime','collectorReceivedAt'),
        'handler_to_write_request':('handlerEnteredAt','writeRequestedAt'),
        'local_caller_to_write_request':('collectorReceivedAt','writeRequestedAt'),
        'write_request_to_ack':('writeRequestedAt','storedAt'),
        'event_to_cloudwatch_ingestion':('eventTime','ingestionTime'),
        'cloudwatch_ingestion_to_read':('ingestionTime','readAt'),
        'read_to_ack':('readAt','storedAt'),
    }
    selected={}
    for receipt in stored_receipts:
        if receipt.get('storedAt') and receipt.get('eventID') in origins:
            eid=receipt['eventID']
            if eid not in selected or timestamp(receipt['storedAt'])<timestamp(selected[eid]['storedAt']): selected[eid]=receipt
    output={}
    for name,(start,end) in definitions.items():
        values=[]
        for eid,r in selected.items():
            fields=dict(r,eventTime=origins[eid][0])
            if fields.get(start) and fields.get(end):
                values.append((timestamp(fields[end])-timestamp(fields[start])).total_seconds())
        values.sort()
        output[name]=dict(samples=len(values),negative_count=sum(x<0 for x in values),
            statistics=dict(mean_seconds=statistics.mean(values),median_seconds=statistics.median(values),
                p95_seconds=values[math.ceil(.95*len(values))-1],max_seconds=max(values)) if values else None)
    return output


def summarize(events,receipts):
    origins=defaultdict(list);stored=defaultdict(list)
    for event in events:
        d=event.get('detail',event);origins[d['eventID']].append(d.get('eventTime',d.get('timestamp')))
    for r in receipts:
        if r.get('storedAt'): stored[r['eventID']].append(r['storedAt'])
    for values in origins.values():
        if len(set(values))!=1: raise ValueError('conflicting_event_time_for_eventID')
    matched=sorted(origins.keys() & stored.keys())
    values=sorted((min(timestamp(s) for s in stored[e])-timestamp(origins[e][0])).total_seconds() for e in matched)
    stats=dict(mean_seconds=statistics.mean(values),median_seconds=statistics.median(values),
        p95_seconds=values[max(0,math.ceil(.95*len(values))-1)],max_seconds=max(values)) if values else None
    return dict(source_records=sum(map(len,origins.values())),receipt_records=sum(map(len,stored.values())),
        matched=len(matched),missing=len(origins.keys()-stored.keys()),unexpected=len(stored.keys()-origins.keys()),
        source_duplicates=sum(len(v)-1 for v in origins.values()),storage_duplicates=sum(len(v)-1 for v in stored.values()),
        negative_latency_count=sum(v<0 for v in values),statistics=stats,
        stages=stage_statistics(origins,receipts),
        source_precision='fractional_seconds' if any('.' in v[0] for v in origins.values()) else 'seconds',
        caveat='Event-time precision, delivery delay and clock skew bound accuracy; not a millisecond-accuracy measurement.')

def load(path): return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--events',required=True);p.add_argument('--receipts',nargs='+',required=True)
    args=p.parse_args();events=load(args.events)
    print(json.dumps({'receipt_file_count':len(args.receipts),'repetition_count':None,'note':'File count does not establish independent repetitions; keep run provenance separately.','receipt_sets':[dict(path=f,**summarize(events,load(f))) for f in args.receipts]},indent=2))
