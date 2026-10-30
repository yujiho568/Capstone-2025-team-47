"""Export loader and production trainer. Shared v2 preprocessing is authoritative."""
import json
import os
from pathlib import Path
from pipeline.ueba.models import train
from io_util import load_dynamodb_json_folder, load_parquet_folder_local

def main():
    root=os.environ.get('SM_INPUT_DIR','/opt/ml/processing/input')
    df=load_dynamodb_json_folder(root)
    if df.empty: df=load_parquet_folder_local(root)
    required={'userId','eventID','timestamp','eventName'}
    if df.empty or not required.issubset(df.columns): raise RuntimeError('v2_export_required')
    rows=[r for r in df.to_dict('records') if isinstance(r.get('eventID'),str)]
    version=os.environ['MODEL_VERSION']
    result=train(rows,Path(os.environ.get('SM_MODELS_DIR','/opt/ml/processing/models'))/'bundles',
                 version,minimum=int(os.environ.get('MIN_TRAIN_EVENTS','3000')))
    result['version']=version
    out=Path(os.environ.get('SM_RESULTS_DIR','/opt/ml/processing/results'))/'training'/version
    out.mkdir(parents=True,exist_ok=True)
    (out/'training-status.json').write_text(json.dumps(result))
    return 0
if __name__=='__main__': raise SystemExit(main())
