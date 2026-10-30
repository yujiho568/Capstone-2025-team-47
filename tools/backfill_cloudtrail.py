"""Prepare replay JSONL from downloaded CloudTrail logs; no AWS writes or invented IDs."""
import argparse,gzip,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline.ueba.events import normalize

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('files',nargs='+');p.add_argument('--output',required=True)
    args=p.parse_args();count=0
    with open(args.output,'x') as out:
        for name in args.files:
            opener=gzip.open if name.endswith('.gz') else open
            with opener(name,'rt') as f: data=json.load(f)
            for detail in data['Records']:
                event={'detail':detail}
                normalize(event) # fail rather than silently drop invalid logs
                out.write(json.dumps(event)+'\n');count+=1
    print(f'Prepared {count} original eventID records. Review before replay; no resource modified.')
if __name__=='__main__': main()
