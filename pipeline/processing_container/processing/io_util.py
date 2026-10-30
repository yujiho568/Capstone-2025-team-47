"""Strict export loading: don't silently train on partial corrupt files."""
import gzip
import json
from pathlib import Path
import pandas as pd
from boto3.dynamodb.types import TypeDeserializer

def load_dynamodb_json_folder(root):
    rows=[]; deser=TypeDeserializer()
    paths=sorted(Path(root).rglob('*.json'))+sorted(Path(root).rglob('*.json.gz'))
    for p in paths:
        if p.name.startswith('manifest'): continue
        opener=gzip.open if p.suffix=='.gz' else open
        with opener(p,'rt') as f:
            for line in f:
                if not line.strip(): continue
                obj=json.loads(line)
                if 'Item' not in obj: continue
                row={k:deser.deserialize(v) for k,v in obj['Item'].items()}
                if row.get('sk')!='DEDUP': rows.append(row)
    return pd.DataFrame(rows)

def load_parquet_folder_local(root):
    frames=[pd.read_parquet(p) for p in sorted(Path(root).rglob('*.parquet'))]
    return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
