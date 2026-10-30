import json
from datetime import datetime, timezone
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from .events import digest, history, windows, parse_time

def realtime_key(item,version):
    return f"results/realtime/{digest(item['userId'])}/{version}/{digest(item['accountId']+':'+item['eventID'])}.json"

def input_digest(seq,initial):
    value=dict(initial=initial,events=[{k:r[k] for k in ('userId','timestamp','eventID','eventName')} for r in seq])
    return digest(json.dumps(value,sort_keys=True,separators=(',',':')))


class Detector:
    def __init__(self,table,s3,bucket,bundle,events=None,*,alert_max_age_seconds=None,now=None):
        self.table,self.s3,self.bucket,self.bundle,self.events=table,s3,bucket,bundle,events
        if events is not None and (type(alert_max_age_seconds) is not int or not 1<=alert_max_age_seconds<=86400):
            raise ValueError('explicit_alert_age_policy_required')
        self.alert_max_age_seconds=alert_max_age_seconds
        self.now=now or (lambda:datetime.now(timezone.utc))

    def process(self,item):
        key=realtime_key(item,self.bundle.version)
        try:
            saved=self.s3.get_object(Bucket=self.bucket,Key=key)
            out=json.loads(saved['Body'].read())
        except ClientError as exc:
            if exc.response['Error']['Code'] not in ('NoSuchKey','404'): raise
            rows=history(self.table,item)
            sample=list(windows(rows))
            if not sample: return {'status':'insufficient_history','count':len(rows)}
            seq,initial=sample[-1]
            if seq[-1]['eventID']!=item['eventID']: raise RuntimeError('history_inconsistent')
            out=dict(ok=True,eventID=item['eventID'],userId=item['userId'],
                     timestamp=item['timestamp'],eventName=item['eventName'],
                     modelVersion=self.bundle.version,analysisKind='realtime',analysisVersion='realtime-v1',
                     inputEventIDs=[r['eventID'] for r in seq],inputDigest=input_digest(seq,initial),
                     initial_session=initial,
                     embedding_dim=self.bundle.d2v.vector_size,
                     result=self.bundle.predict(seq,initial))
            try:
                self.s3.put_object(Bucket=self.bucket,Key=key,Body=json.dumps(out,allow_nan=False).encode(),
                                   ContentType='application/json',IfNoneMatch='*')
            except ClientError as exc:
                if exc.response['Error']['Code']!='PreconditionFailed': raise
                out=json.loads(self.s3.get_object(Bucket=self.bucket,Key=key)['Body'].read())
        # Result first, notification second. Retries republish same result ID; consumers must dedup.
        result=out['result']
        notification_status='disabled'
        age=(self.now()-parse_time(item['timestamp'])).total_seconds()
        if self.events is not None and (age<0 or age>self.alert_max_age_seconds):
            notification_status='historical_or_future_event_suppressed'
        elif self.events is not None and (result.get('is_noise') or result.get('is_anomaly')):
            response=self.events.put_events(Entries=[dict(Source='ct.realtime',
                DetailType='Security.AnomalyDetected',Detail=json.dumps(dict(resultKey=key,
                eventID=item['eventID'],modelVersion=self.bundle.version,userId=item['userId'],
                risk=result['risk'])))])
            if response.get('FailedEntryCount',0): raise RuntimeError('anomaly_delivery_failed')
            notification_status='published'
        return dict(status='complete',key=key,payload=out,notificationStatus=notification_status)

    def batch(self,event):
        failed=[]
        for rec in event.get('Records',[]):
            if rec.get('eventName')!='INSERT': continue
            image=rec.get('dynamodb',{}).get('NewImage',{})
            # Dedup markers are not behaviour events.
            if image.get('sk',{}).get('S')=='DEDUP': continue
            try:
                item={k:TypeDeserializer().deserialize(v) for k,v in image.items()}
                self.process(item)
            except Exception:
                seq=rec['dynamodb']['SequenceNumber']
                failed.append({'itemIdentifier':seq})
                # Lambda checkpoints at the lowest failed sequence; don't publish later records.
                break
        return {'batchItemFailures':failed}
