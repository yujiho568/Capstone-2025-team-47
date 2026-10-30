"""Offline state graph checks complement terraform validate (which treats ASL as a string)."""
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_stepfunctions_graph_has_no_dangling_targets_or_unbounded_quota_retry():
    source=(ROOT/'pipeline/UEBA/modules/ct-pipeline/sfn.tf').read_text()
    states=set(re.findall(r'^      (\w+)\s*=',source,re.M))
    targets=set(re.findall(r'\b(?:Next|Default|StartAt)"?\s*[:=]\s*"(\w+)"',source))
    assert targets<=states,targets-states
    # Failure branch must terminate; no retry cycle returning to job creation.
    catch=re.search(r'Catch = \[(.*?)\n        \]',source,re.S).group(1)
    assert 'FailProcessing' in catch
    assert 'TimeoutSeconds' in source and 'MaxRuntimeInSeconds' in source

def test_summary_uses_job_version_and_preserves_existing_record(aws,monkeypatch):
    import importlib.util,json,boto3
    t,s3=aws
    path=ROOT/'pipeline/UEBA/modules/ct-pipeline/lambda/ct-summarize/handler.py'
    spec=importlib.util.spec_from_file_location('summary_handler',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    monkeypatch.setenv('BUCKET','ueba-results');monkeypatch.setenv('RESULTS_TABLE','events')
    event={'job':{'jobName':'ct-job-1'}}
    key='results/training/ct-job-1/training-status.json'
    body={'version':'ct-job-1','status':'trained','count':3000}
    s3.put_object(Bucket='ueba-results',Key=key,Body=json.dumps(body))
    assert mod.lambda_handler(event,None)['trainingStatus']=='trained'
    assert mod.lambda_handler(event,None)['ok']
    body['count']=4000;s3.put_object(Bucket='ueba-results',Key=key,Body=json.dumps(body))
    import pytest
    with pytest.raises(RuntimeError): mod.lambda_handler(event,None)
