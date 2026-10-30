"""Pinned model version; changing MODEL_VERSION updates Lambda configuration/cold starts."""
import json
import os
from pathlib import Path
import boto3
from pipeline.ueba.models import Bundle, ModelUnavailable
from pipeline.ueba.detection import Detector

_bundle=None

def load_bundle(s3,bucket,version):
    global _bundle
    if not version or '/' in version or '..' in version: raise ModelUnavailable('MODEL_VERSION_required')
    if _bundle is not None and _bundle.version==version: return _bundle
    root=Path('/tmp/ueba-models'); path=root/version; path.mkdir(parents=True,exist_ok=True)
    for name in ('manifest.json','doc2vec.bin','detectors.joblib'):
        try: s3.download_file(bucket,f'models/bundles/{version}/{name}',str(path/name))
        except Exception as exc: raise ModelUnavailable('model_download_failed') from exc
    _bundle=Bundle(root,version)
    return _bundle

def lambda_handler(event, context):
    if not isinstance(event,dict) or not isinstance(event.get('Records'),list):
        raise ValueError('stream_records_required')
    eligible=[r for r in event['Records'] if r.get('eventName')=='INSERT'
              and 'eventID' in r.get('dynamodb',{}).get('NewImage',{})]
    if not eligible: return {'batchItemFailures':[]}
    s3=boto3.client('s3'); bucket=os.environ['BUCKET']
    # A missing bundle is an operational failure, never a normal/high-risk result.
    model=load_bundle(s3,bucket,os.environ.get('MODEL_VERSION',''))
    return Detector(boto3.resource('dynamodb').Table(os.environ['EVENT_TABLE']),s3,bucket,model,
                    boto3.client('events') if os.environ.get('EMIT_ANOMALIES','false')=='true' else None).batch(event)
