"""Validate correction publication without importing the ML/runtime package."""
import hashlib,json
from botocore.exceptions import ClientError


def digest(value): return hashlib.sha256(value.encode()).hexdigest()


def verify_publication(s3,bucket,principal,key,payload,cache):
    model=payload['modelVersion'];analysis=payload['analysisVersion'];owner=digest(principal)
    manifest_key=f'analysis-runs/{owner}/{model}/{analysis}/complete.json'
    if manifest_key not in cache:
        try:
            response=s3.get_object(Bucket=bucket,Key=manifest_key)
            body=response['Body'].read(1024*1024+1)
            if len(body)>1024*1024: raise ValueError('object_too_large')
            cache[manifest_key]=json.loads(body)
        except ClientError as exc:
            if exc.response['Error']['Code'] not in ('NoSuchKey','404'): raise
            cache[manifest_key]=None
    manifest=cache[manifest_key]
    base=f'results/realtime/{owner}/{model}/'
    suffix=digest(principal.split(':',1)[0]+':'+payload['eventID'])+'.json'
    if key!=base+'reanalysis/'+analysis+'/'+suffix or payload.get('supersedesKey') not in (None,base+suffix):
        raise ValueError('invalid_analysis_lineage')
    if (not isinstance(manifest,dict) or manifest.get('status')!='complete'
        or manifest.get('userId')!=principal or manifest.get('modelVersion')!=model
        or manifest.get('analysisVersion')!=analysis or manifest.get('snapshotDigest')!=payload['snapshotDigest']
        or not isinstance(manifest.get('resultKeys'),list) or len(manifest['resultKeys'])>1000
        or key not in manifest['resultKeys']):
        raise ValueError('analysis_run_incomplete')
