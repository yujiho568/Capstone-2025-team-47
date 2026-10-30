"""Index a specific training job, never a mutable latest-date stats object."""
import os,json,re
import boto3
from botocore.exceptions import ClientError

def lambda_handler(event,context):
    version=event['job']['jobName']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',version): raise ValueError('invalid_model_version')
    stats=json.loads(boto3.client('s3').get_object(Bucket=os.environ['BUCKET'],
        Key=f'results/training/{version}/training-status.json')['Body'].read())
    if stats.get('version')!=version or stats.get('status') not in ('trained','skipped'):
        raise ValueError('training_status_inconsistent')
    key={'pk':{'S':'MODEL#'+version},'sk':{'S':'SUMMARY'}}
    payload=json.dumps(stats,sort_keys=True)
    ddb=boto3.client('dynamodb')
    try:
        ddb.put_item(TableName=os.environ['RESULTS_TABLE'],Item={**key,'payload':{'S':payload}},
                     ConditionExpression='attribute_not_exists(pk)')
    except ClientError as exc:
        if exc.response['Error']['Code']!='ConditionalCheckFailedException': raise
        existing=ddb.get_item(TableName=os.environ['RESULTS_TABLE'],Key=key,ConsistentRead=True)['Item']
        if existing['payload']['S']!=payload: raise RuntimeError('immutable_summary_changed')
    return {'ok':True,'modelVersion':version,'trainingStatus':stats['status']}
