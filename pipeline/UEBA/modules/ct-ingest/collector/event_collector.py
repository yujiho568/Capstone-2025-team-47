import os
import boto3
from botocore.config import Config
from pipeline.ueba.events import Collector, iso
from datetime import datetime, timezone

def handler(event, context):
    entered=iso(datetime.now(timezone.utc))
    sdk=Config(connect_timeout=3,read_timeout=5,retries={'mode':'standard','total_max_attempts':2})
    return Collector(boto3.resource('dynamodb',config=sdk).Table(os.environ['USER_EVENT_TABLE']),
                     boto3.client('s3',config=sdk), os.environ['FAILURE_BUCKET'],
                     int(os.environ.get('RETENTION_DAYS','90'))).collect(event, handler_entered_at=entered)
