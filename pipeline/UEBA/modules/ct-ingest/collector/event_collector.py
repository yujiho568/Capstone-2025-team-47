import os
import boto3
from pipeline.ueba.events import Collector

def handler(event, context):
    return Collector(boto3.resource('dynamodb').Table(os.environ['USER_EVENT_TABLE']),
                     boto3.client('s3'), os.environ['FAILURE_BUCKET'],
                     int(os.environ.get('RETENTION_DAYS','90'))).collect(event)
