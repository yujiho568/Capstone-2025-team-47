"""Measure current-clock synthetic collection against Moto, never real AWS latency."""
import argparse
import json
import logging
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.mock_setup import mock_services
from tools.latency import summarize
from pipeline.ueba.events import Collector, iso


def stats(values):
    ordered = sorted(values)
    return dict(mean_seconds=statistics.mean(values), median_seconds=statistics.median(values),
                p95_seconds=ordered[math.ceil(.95 * len(ordered)) - 1], max_seconds=max(values))


def measure(count=30, repetitions=3, output=None):
    if not 1 <= count <= 1000 or not 1 <= repetitions <= 10:
        raise ValueError('count must be 1..1000; repetitions must be 1..10')
    output = Path(output) if output else ROOT / '.demo' / 'latency' / str(uuid4())
    output.mkdir(parents=True, exist_ok=False)
    report = dict(mode='local_moto_only', aws_cloudtrail_measured=False,
                  aws_cloudwatch_measured=False, managed_delivery_measured=False,
                  requested_events_per_repetition=count, completed_repetitions=0, warmups_per_repetition=1,
                  exclusions='Resource creation and one warmup per repetition excluded. No intentional delay injected.',
                  repetitions=[])
    logger = logging.getLogger('pipeline.ueba.events')
    old_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        with mock_services():
            import boto3
            s3 = boto3.client('s3')
            s3.create_bucket(Bucket='latency-invalid-only')
            for run in range(repetitions):
                table = boto3.resource('dynamodb').create_table(
                    TableName=f'latency-events-{run}', BillingMode='PAY_PER_REQUEST',
                    KeySchema=[dict(AttributeName='pk', KeyType='HASH'), dict(AttributeName='sk', KeyType='RANGE')],
                    AttributeDefinitions=[dict(AttributeName=n, AttributeType='S') for n in ('pk', 'sk')])
                collector = Collector(table, s3, 'latency-invalid-only')

                def event(eid):
                    return {'detail': dict(eventID=eid, eventTime=iso(datetime.now(timezone.utc)),
                        eventName='ListBuckets', userIdentity=dict(accountId='123456789012', principalId='LOCAL-LATENCY'))}

                collector.collect(event(f'warmup-{run}'))
                events, receipts, durations = [], [], []
                for i in range(count):
                    e = event(f'local-{run}-{i}-{uuid4()}')
                    received = iso(datetime.now(timezone.utc))
                    start = perf_counter()
                    receipt = collector.collect(e)
                    durations.append(perf_counter() - start)
                    if receipt['status'] != 'stored':
                        raise RuntimeError('measurement_event_not_stored')
                    receipt['collectorReceivedAt'] = received
                    events.append(e)
                    receipts.append(receipt)
                duplicate = collector.collect(events[0])
                rows = []; scan = {}
                while True:
                    page = table.scan(**scan)
                    rows.extend(r for r in page['Items'] if r.get('eventID', '').startswith('local-'))
                    if not page.get('LastEvaluatedKey'):
                        break
                    scan['ExclusiveStartKey'] = page['LastEvaluatedKey']
                ids = [r['eventID'] for r in rows]
                if len(ids) != count or len(set(ids)) != count:
                    raise RuntimeError('stored_event_count_mismatch')
                first = next(r for r in rows if r['eventID'] == events[0]['detail']['eventID'])
                measured = summarize(events, receipts)
                measured.update(run=run + 1, stored_rows=len(rows), duplicate_replay_status=duplicate['status'],
                    monotonic_collector_call=stats(durations),
                    sample=dict(eventID=first['eventID'], eventTime=first['timestamp'],
                        collectorReceivedAt=receipts[0]['collectorReceivedAt'], writeRequestedAt=first['writeRequestedAt'],
                        storedAt=receipts[0]['storedAt']))
                (output / f'run-{run+1}-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
                (output / f'run-{run+1}-receipts.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in receipts))
                report['repetitions'].append(measured)
                report['completed_repetitions'] += 1
    finally:
        logger.setLevel(old_level)
    report['completed_events'] = sum(r['matched'] for r in report['repetitions'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return output, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=30)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--output')
    args = parser.parse_args()
    path, report = measure(args.count, args.repetitions, args.output)
    print(json.dumps(dict(output=str(path), **report), indent=2))
