"""Unwrap retained failure payload to JSONL for review; never invokes/deletes AWS resources."""
import argparse,json
from pathlib import Path

def unwrap(obj):
    if isinstance(obj,str): return unwrap(json.loads(obj))
    if 'Body' in obj: return unwrap(obj['Body']) # exported SQS message
    if 'original' in obj: return [obj['original']]
    if 'requestPayload' in obj: return unwrap(obj['requestPayload'])
    if 'Records' in obj and any('dynamodb' in r for r in obj['Records']): return [obj]
    if 'detail' in obj: return [obj]
    raise ValueError('unsupported_failure_envelope_or_payload_missing')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive');p.add_argument('--output',required=True)
    a=p.parse_args();data=json.loads(Path(a.archive).read_text())
    rows=unwrap(data)
    with open(a.output,'x') as f:
        for row in rows: f.write(json.dumps(row)+'\n')
    print(f'{len(rows)} replay payload(s) written. Review before explicit Lambda invocation; no queue message was deleted.')
