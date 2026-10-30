"""Canonical v2 CloudTrail storage and shared chronological session policy."""
import hashlib
import json
import logging
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

HASH_POLICY = "cloudtrail-detail-v1"
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

def content_hash(event):
    """Hash CloudTrail detail only; EventBridge delivery metadata is not content.

    JSON object key order and equivalent eventTime timezone notation are normalized.
    All other detail fields (including userIdentity/requestParameters) are compared.
    """
    if isinstance(event,str): event=json.loads(event)
    detail=dict(event['detail'])
    detail['eventTime']=iso(parse_time(detail['eventTime']))
    return digest(json.dumps(detail,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False))


class Collector:
    def __init__(self, table, s3, failure_bucket, retention_days=90):
        self.table, self.s3, self.failure_bucket = table, s3, failure_bucket
        if retention_days < 1: raise ValueError('retention_days')
        self.retention_days = retention_days

    def archive(self,event,reason,category='invalid',**metadata):
        raw=json.dumps(event,sort_keys=True,ensure_ascii=False,default=str)
        key=category+'/'+digest(raw+reason)+'.json'
        self.s3.put_object(Bucket=self.failure_bucket,Key=key,
            Body=json.dumps(dict(original=event,reason=reason,recordedAt=iso(datetime.now(UTC)),**metadata),
                            ensure_ascii=False,default=str).encode(),ContentType='application/json')
        result={'status':'invalid' if category=='invalid' else 'conflict','failureKey':key,'reason':reason}
        logger.warning(json.dumps(result))
        return result

    def collect(self, event, *, handler_entered_at=None):
        try:
            item = normalize(event, self.retention_days)
            incoming_hash = content_hash(event)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            # Persist original input, not just a log message; archive failure must retry.
            reason=type(exc).__name__
            if isinstance(exc,KeyError) and exc.args and exc.args[0] in ('detail','userIdentity','accountId','eventID','eventTime','eventName'):
                reason='missing_field:'+exc.args[0]
            return self.archive(event,reason)
        marker = dict(pk='EVENT#'+item['accountId']+'#'+item['eventID'], sk='DEDUP',
                      expiresAt=item['expiresAt'],contentHash=incoming_hash,hashPolicy=HASH_POLICY,
                      eventPk=item['pk'],eventSk=item['sk'])
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
                    existing=self.table.get_item(Key={'pk':marker['pk'],'sk':'DEDUP'},ConsistentRead=True).get('Item')
                    if not existing:
                        # TTL race or uncertain state: don't acknowledge a duplicate.
                        raise
                    if existing.get('hashPolicy')!=HASH_POLICY or not existing.get('contentHash'):
                        return self.archive(event,'legacy_or_unknown_hash_policy','conflicts',eventID=item['eventID'])
                    if existing['contentHash']!=incoming_hash:
                        return self.archive(event,'content_hash_mismatch','conflicts',eventID=item['eventID'],
                                            storedHash=existing['contentHash'],incomingHash=incoming_hash,hashPolicy=HASH_POLICY)
                    expiry=existing.get('expiresAt')
                    if not isinstance(expiry,(int,float,Decimal)) or expiry<=datetime.now(UTC).timestamp():
                        return self.archive(event,'marker_retention_expired_or_unknown','conflicts',eventID=item['eventID'])
                    if not existing.get('eventPk') or not existing.get('eventSk'):
                        return self.archive(event,'marker_record_pointer_missing','conflicts',eventID=item['eventID'])
                    stored=self.table.get_item(Key={'pk':existing['eventPk'],'sk':existing['eventSk']},ConsistentRead=True).get('Item')
                    if not stored or any(stored.get(k)!=item[k] for k in ('accountId','userId','eventID','timestamp','eventName')):
                        return self.archive(event,'behavior_record_missing_or_inconsistent','conflicts',eventID=item['eventID'])
                    return {'status':'duplicate', 'eventID':item['eventID'],'hashPolicy':HASH_POLICY,'contentHash':incoming_hash}
            raise
        # This acknowledgement timestamp is sampled after DynamoDB returns success.
        # The item itself contains writeRequestedAt, not a falsely labelled completion time.
        receipt={'status':'stored','eventID':item['eventID'],'storedAt':iso(datetime.now(UTC)),
                 'hashPolicy':HASH_POLICY,'contentHash':incoming_hash,'writeRequestedAt':item['writeRequestedAt']}
        if handler_entered_at is not None: receipt['handlerEnteredAt']=handler_entered_at
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
