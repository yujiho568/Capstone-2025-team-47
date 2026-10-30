"""Canonical v2 CloudTrail storage and shared chronological session policy."""
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

UTC = timezone.utc
logger=logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def parse_time(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timezone_required')
    return dt.astimezone(UTC)

def iso(dt):
    return dt.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def normalize(event, retention_days=90, now=None):
    if isinstance(event, str):
        event = json.loads(event)
    if not isinstance(event, dict):
        raise ValueError('object_required')
    d = event['detail']
    ident = d['userIdentity']
    account = ident['accountId']
    principal = ident.get('principalId') or ident.get('arn')
    eid, name = d['eventID'], d['eventName']
    if not (isinstance(account, str) and len(account)==12 and account.isdigit()):
        raise ValueError('account_invalid')
    for val in (principal, eid, name):
        if not isinstance(val, str) or not val or len(val)>512:
            raise ValueError('required_string_invalid')
    if d.get('recipientAccountId', account) != account:
        # Account scope follows actor identity; recipient remains in raw event.
        pass
    ts = iso(parse_time(d['eventTime']))
    now = now or datetime.now(UTC)
    user = account + ':' + principal
    return dict(pk='USER#'+digest(user), sk=ts+'#'+eid, userId=user,
                accountId=account, principalId=principal, eventID=eid,
                timestamp=ts, eventName=name, writeRequestedAt=iso(now),
                expiresAt=int((now+timedelta(days=retention_days)).timestamp()),
                rawEvent=json.dumps(event, separators=(',', ':'), allow_nan=False))

class Collector:
    def __init__(self, table, s3, failure_bucket, retention_days=90):
        self.table, self.s3, self.failure_bucket = table, s3, failure_bucket
        if retention_days < 1: raise ValueError('retention_days')
        self.retention_days = retention_days

    def collect(self, event):
        try:
            item = normalize(event, self.retention_days)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            # Persist original input, not just a log message; archive failure must retry.
            raw = json.dumps(event, ensure_ascii=False, default=str)
            key = 'invalid/'+digest(raw)+'.json'
            reason=type(exc).__name__
            if isinstance(exc,KeyError) and exc.args and exc.args[0] in ('detail','userIdentity','accountId','eventID','eventTime','eventName'):
                reason='missing_field:'+exc.args[0]
            self.s3.put_object(Bucket=self.failure_bucket, Key=key,
                Body=json.dumps({'original':event, 'reason':reason,
                                 'recordedAt':iso(datetime.now(UTC))}).encode(),
                ContentType='application/json')
            return {'status':'invalid', 'failureKey':key}
        marker = dict(pk='EVENT#'+item['accountId']+'#'+item['eventID'], sk='DEDUP',
                      expiresAt=item['expiresAt'])
        # Resource client serializes native Python values in transact_write_items.
        def put(row):
            return {'Put':{'TableName':self.table.name, 'Item':row,
                           'ConditionExpression':'attribute_not_exists(pk)'}}
        try:
            self.table.meta.client.transact_write_items(TransactItems=[put(marker), put(item)])
        except ClientError as exc:
            if exc.response['Error']['Code']=='TransactionCanceledException':
                reasons=exc.response.get('CancellationReasons', [])
                # Only a conditional marker collision is an accepted duplicate.
                if (len(reasons)==2 and reasons[0].get('Code')=='ConditionalCheckFailed'
                    and reasons[1].get('Code') in ('None','ConditionalCheckFailed')):
                    return {'status':'duplicate', 'eventID':item['eventID']}
            raise
        # This acknowledgement timestamp is sampled after DynamoDB returns success.
        # The item itself contains writeRequestedAt, not a falsely labelled completion time.
        receipt={'status':'stored','eventID':item['eventID'],'storedAt':iso(datetime.now(UTC))}
        logger.info(json.dumps(receipt))
        return receipt

def history(table, item):
    """Consistent reads up to this event's deterministic (time,eventID) key.

    Read at most 41 records: after endpoint 40, no initial window is possible.
    Earlier history cannot affect the latest 20-event window or initial flag.
    """
    rows=[]; cursor=None; limit=41
    while True:
        args=dict(KeyConditionExpression=Key('pk').eq(item['pk']) & Key('sk').lte(item['sk']),
                  ScanIndexForward=False, ConsistentRead=True, Limit=min(100, limit-len(rows)))
        if cursor: args['ExclusiveStartKey']=cursor
        res=table.query(**args)
        for row in res['Items']:
            if rows and (parse_time(rows[-1]['timestamp'])-parse_time(row['timestamp'])).total_seconds()>=1800:
                return list(reversed(rows))
            rows.append(row)
        cursor=res.get('LastEvaluatedKey')
        if not cursor: return list(reversed(rows))
        if len(rows)>=limit: return list(reversed(rows))

def sessions(rows, gap_minutes=30):
    groups={}
    for row in rows:
        groups.setdefault(row['userId'], []).append(row)
    result=[]
    for user in sorted(groups):
        ordered=sorted(groups[user], key=lambda x:(parse_time(x['timestamp']),x['eventID']))
        current=[]
        for row in ordered:
            if current and (parse_time(row['timestamp'])-parse_time(current[-1]['timestamp'])).total_seconds()>=gap_minutes*60:
                result.append(current); current=[]
            current.append(row)
        if current: result.append(current)
    return result

def windows(rows):
    """20 events, never crossing user/session. Initial: endpoints 20,25,30,35,40."""
    for segment in sessions(rows):
        for end in range(20, len(segment)+1):
            yield segment[end-20:end], end in (20,25,30,35,40)
