"""Plan archival corrections offline. --execute writes only to a local result directory.

For live S3 publication, use execute_reanalysis from a separately reviewed runner.
This CLI has no AWS clients and never sends notifications.
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path
from botocore.exceptions import ClientError
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.ueba.reanalysis import plan_reanalysis,execute_reanalysis

class LocalResults:
    """Exclusive-create local adapter; compatible with the used S3 operations only."""
    def __init__(self,root): self.root=Path(root).resolve()
    def path(self,key):
        p=self.root/key
        if not p.resolve().is_relative_to(self.root): raise ValueError('object_path_escape')
        return p
    def get_object(self,*,Bucket,Key):
        path=self.path(Key)
        if not path.is_file(): raise ClientError({'Error':{'Code':'NoSuchKey'}},'GetObject')
        if path.stat().st_size>1024*1024: raise ValueError('object_size_limit')
        return {'Body':io.BytesIO(path.read_bytes())}
    def put_object(self,*,Bucket,Key,Body,IfNoneMatch,**kwargs):
        if IfNoneMatch!='*': raise ValueError('exclusive_create_required')
        path=self.path(Key);path.parent.mkdir(parents=True,exist_ok=True)
        import tempfile
        temp=None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as f:
                temp=Path(f.name);f.write(Body);f.flush();os.fsync(f.fileno())
            try: os.link(temp,path) # Atomically publish complete bytes, never overwrite.
            except FileExistsError:
                raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject') from None
        finally:
            if temp is not None: temp.unlink(missing_ok=True)
        return {}

def read_bounded(path):
    path=Path(path)
    if path.stat().st_size>20*1024*1024: raise ValueError('input_file_limit')
    return json.loads(path.read_text())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True);parser.add_argument('--late-events',required=True,help='JSON array of CloudTrail envelopes')
    parser.add_argument('--execute',action='store_true');parser.add_argument('--model-root');parser.add_argument('--model-version')
    parser.add_argument('--result-dir');parser.add_argument('--analysis-version');parser.add_argument('--max-seconds',type=int,default=120)
    parser.add_argument('--max-events',type=int,default=5000);parser.add_argument('--max-results',type=int,default=200)
    args=parser.parse_args()
    plan=plan_reanalysis(read_bounded(args.snapshot),read_bounded(args.late_events),max_events=args.max_events,max_results=args.max_results)
    if not args.execute:
        print(json.dumps(dict(status='dry_run',planStatus=plan['status'],userId=plan['userId'],snapshotDigest=plan['snapshotDigest'],
            affectedEventIDs=[r['eventID'] for r in plan['affected']],awsRequests=0)))
        return
    if not args.model_root or not args.model_version or not args.result_dir:
        parser.error('local execution requires --model-root --model-version --result-dir')
    from pipeline.ueba.models import Bundle
    result=execute_reanalysis(plan,LocalResults(args.result_dir),'local-only',Bundle(args.model_root,args.model_version),
                             analysis_version=args.analysis_version,max_seconds=args.max_seconds)
    print(json.dumps(dict(**result,publication='local_files_only',awsRequests=0)))
if __name__=='__main__': main()
