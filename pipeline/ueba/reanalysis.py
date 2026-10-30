"""Bounded, immutable archival reanalysis. Never publishes notifications.

A checksum proves snapshot integrity, not source completeness. Completeness and
session boundaries require independently reviewed archive provenance.
"""
import json
import re
from datetime import datetime,timezone
from decimal import Decimal
from time import monotonic
from .events import normalize,iso,parse_time,digest,windows
from .detection import realtime_key,input_digest
from botocore.exceptions import ClientError

FIELDS=('userId','accountId','eventID','eventName','timestamp','expiresAt')

class ReanalysisUnavailable(RuntimeError): pass


def canonical_rows(rows):
    result=[]
    for row in rows:
        r={k:row[k] for k in FIELDS}
        for key in ('userId','accountId','eventID','eventName'):
            if not isinstance(r[key],str) or not r[key] or len(r[key])>1024: raise ValueError('invalid_row_string')
        if len(r['accountId'])!=12 or not r['accountId'].isdigit() or not r['userId'].startswith(r['accountId']+':'):
            raise ValueError('invalid_principal')
        r['expiresAt']=int(r['expiresAt'])
        r['timestamp']=iso(parse_time(r['timestamp']))
        result.append(r)
    return sorted(result,key=lambda r:(r['timestamp'],r['eventID']))


def rows_digest(rows):
    return digest(json.dumps(canonical_rows(rows),sort_keys=True,separators=(',',':')))


def make_snapshot(rows,*,coverage_start,coverage_end,source,completeness_evidence,session_boundaries_verified=False):
    """Operator preparation helper. Flags are attestations, not an automatic proof."""
    normalized=canonical_rows(rows)
    return dict(schemaVersion=1,source=source,completenessEvidence=completeness_evidence,
        sessionBoundariesVerified=session_boundaries_verified,coverageStart=iso(parse_time(coverage_start)),
        coverageEnd=iso(parse_time(coverage_end)),eventCount=len(rows),eventsSha256=rows_digest(rows),events=normalized)


def plan_reanalysis(snapshot,late_events,*,max_events=5000,max_results=200,now=None):
    if not 1<=max_events<=10000 or not 1<=max_results<=1000: raise ValueError('invalid_limits')
    if snapshot.get('schemaVersion')!=1 or snapshot.get('sessionBoundariesVerified') is not True:
        raise ReanalysisUnavailable('complete_session_coverage_required')
    if snapshot.get('source') not in ('reviewed-archive','synthetic-fixture') or not isinstance(snapshot.get('completenessEvidence'),str) or not 1<=len(snapshot['completenessEvidence'])<=2048:
        raise ReanalysisUnavailable('reviewed_archive_provenance_required')
    raw=snapshot.get('events',[])
    if not raw or len(raw)>max_events or not isinstance(late_events,list) or not 1<=len(late_events)<=50:
        raise ReanalysisUnavailable('empty_or_oversized_history')
    try:
        before=canonical_rows(raw)
        if snapshot.get('eventCount')!=len(before) or snapshot.get('eventsSha256')!=rows_digest(before):
            raise ReanalysisUnavailable('snapshot_integrity_failed')
        start,end=parse_time(snapshot['coverageStart']),parse_time(snapshot['coverageEnd'])
        now=now or datetime.now(timezone.utc)
        user=before[0]['userId'];account=before[0]['accountId']
        seen={}
        for row in before:
            if row['userId']!=user or row['accountId']!=account: raise ReanalysisUnavailable('mixed_principals')
            if row['eventID'] in seen: raise ReanalysisUnavailable('duplicate_snapshot_eventID')
            if row['expiresAt']<=now.timestamp(): raise ReanalysisUnavailable('history_expired_requires_archive_restore')
            if not start<=parse_time(row['timestamp'])<=end: raise ReanalysisUnavailable('coverage_mismatch')
            seen[row['eventID']]=row
        late=[]
        for event in late_events:
            row=normalize(event,now=now)
            if row['userId']!=user or row['accountId']!=account: raise ReanalysisUnavailable('mixed_principals')
            if not start<=parse_time(row['timestamp'])<=end: raise ReanalysisUnavailable('late_event_outside_coverage')
            previous=seen.get(row['eventID'])
            if previous:
                if any(previous[k]!=row[k] for k in ('userId','accountId','eventID','eventName','timestamp')):
                    raise ReanalysisUnavailable('late_event_content_collision')
                continue
            seen[row['eventID']]=row;late.append(row)
        if len(before)+len(late)>max_events: raise ReanalysisUnavailable('history_limit')
        after=canonical_rows(before+late)
    except (KeyError,ValueError,TypeError,AttributeError) as exc:
        raise ReanalysisUnavailable('invalid_snapshot_or_event') from exc
    previous={seq[-1]['eventID']:(seq,initial) for seq,initial in windows(before)}
    changed=[]
    for seq,initial in windows(after):
        eid=seq[-1]['eventID'];old=previous.get(eid)
        if old is None or input_digest(*old)!=input_digest(seq,initial):
            changed.append(dict(eventID=eid,sequence=seq,initial=initial,
                                beforeDigest=input_digest(*old) if old else None))
    if len(changed)>max_results: raise ReanalysisUnavailable('affected_result_limit')
    if late and not changed: raise ReanalysisUnavailable('insufficient_history_for_late_event')
    return dict(status='planned' if changed else 'no_change',userId=user,snapshotDigest=rows_digest(before),afterDigest=digest(json.dumps([{k:v for k,v in row.items() if k!='expiresAt'} for row in after],sort_keys=True,separators=(',',':'))),
                affected=changed,source=snapshot['source'],coverageStart=snapshot['coverageStart'],
                coverageEnd=snapshot['coverageEnd'],completenessEvidence=snapshot['completenessEvidence'],
                afterEvents=after)


def complete_manifest_key(user,model_version,analysis_version):
    return f'analysis-runs/{digest(user)}/{model_version}/{analysis_version}/complete.json'


def get_json(s3,bucket,key):
    try:
        response=s3.get_object(Bucket=bucket,Key=key)
        body=response['Body'].read(1024*1024+1)
        if len(body)>1024*1024: raise ReanalysisUnavailable('object_size_limit')
        return json.loads(body)
    except ClientError as exc:
        if exc.response['Error']['Code'] in ('NoSuchKey','404'): return None
        raise


def put_immutable(s3,bucket,key,payload):
    try:
        s3.put_object(Bucket=bucket,Key=key,Body=json.dumps(payload,sort_keys=True,allow_nan=False).encode(),
                      ContentType='application/json',IfNoneMatch='*')
    except ClientError as exc:
        if exc.response['Error']['Code']!='PreconditionFailed': raise
        if get_json(s3,bucket,key)!=payload: raise ReanalysisUnavailable('immutable_analysis_conflict')


def execute_reanalysis(plan,s3,bucket,bundle,*,analysis_version=None,max_seconds=120,clock=monotonic):
    if not 1<=max_seconds<=3600: raise ValueError('invalid_time_budget')
    version=bundle.version
    if plan.get('status')=='no_change':
        return dict(status='no_change',modelVersion=version,resultKeys=[],notificationsPublished=0)
    fingerprint=digest(json.dumps(dict(before=plan['snapshotDigest'],after=plan['afterDigest'],model=version,
        coverageStart=plan['coverageStart'],coverageEnd=plan['coverageEnd'],evidence=plan['completenessEvidence']),sort_keys=True))
    analysis_version=analysis_version or 'recovery-'+fingerprint[:32]
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',analysis_version): raise ValueError('invalid_analysis_version')
    complete_key=complete_manifest_key(plan['userId'],version,analysis_version)
    plan_key=complete_key.replace('/complete.json','/plan.json')
    identity=dict(userId=plan['userId'],modelVersion=version,analysisVersion=analysis_version,
                  snapshotDigest=plan['snapshotDigest'],afterDigest=plan['afterDigest'],planFingerprint=fingerprint)
    put_immutable(s3,bucket,plan_key,dict(**identity,eventIDs=[r['eventID'] for r in plan['affected']],
        coverageStart=plan['coverageStart'],coverageEnd=plan['coverageEnd'],source=plan['source'],
        completenessEvidence=plan['completenessEvidence']))
    available={r['eventID']:r for r in plan['afterEvents']}
    deadline=clock()+max_seconds;keys=[]
    for change in plan['affected']:
        if clock()>=deadline: raise ReanalysisUnavailable('time_budget_exhausted_partial_run_not_published')
        seq=change['sequence'];item=seq[-1];initial=change['initial']
        base_key=realtime_key(item,version)
        key=base_key.replace('/'+digest(item['accountId']+':'+item['eventID'])+'.json',
                             '/reanalysis/'+analysis_version+'/'+digest(item['accountId']+':'+item['eventID'])+'.json')
        old=get_json(s3,bucket,base_key)
        if old is not None:
            ids=old.get('inputEventIDs',[])
            try:
                original_seq=[available[eid] for eid in ids]
                valid=(len(ids)==20 and len(set(ids))==20 and ids[-1]==item['eventID']
                    and old.get('userId')==item['userId'] and old.get('modelVersion')==version
                    and type(old.get('initial_session')) is bool
                    and original_seq==sorted(original_seq,key=lambda r:(r['timestamp'],r['eventID']))
                    and old.get('inputDigest')==input_digest(original_seq,old['initial_session']))
            except (KeyError,TypeError): valid=False
            if not valid:
                raise ReanalysisUnavailable('baseline_input_provenance_missing_or_mismatched')
        expected=dict(userId=item['userId'],eventID=item['eventID'],modelVersion=version,
                      analysisKind='reanalysis',analysisVersion=analysis_version,
                      snapshotDigest=plan['snapshotDigest'],inputDigest=input_digest(seq,initial),
                      supersedesKey=base_key if old is not None else None)
        saved=get_json(s3,bucket,key)
        if saved is not None:
            if any(saved.get(k)!=v for k,v in expected.items()): raise ReanalysisUnavailable('immutable_analysis_conflict')
        else:
            payload=dict(**expected,ok=True,timestamp=item['timestamp'],eventName=item['eventName'],
                initial_session=initial,embedding_dim=bundle.d2v.vector_size,
                inputEventIDs=[r['eventID'] for r in seq],result=bundle.predict(seq,initial))
            put_immutable(s3,bucket,key,payload)
        keys.append(key)
    if clock()>=deadline: raise ReanalysisUnavailable('time_budget_exhausted_partial_run_not_published')
    put_immutable(s3,bucket,complete_key,dict(**identity,status='complete',resultKeys=keys))
    return dict(status='complete',analysisVersion=analysis_version,modelVersion=version,
                resultKeys=keys,completeManifestKey=complete_key,notificationsPublished=0)
