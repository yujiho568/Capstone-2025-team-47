"""Deterministic source staging; no opaque embedded Lambda ZIP is deployed."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parents[1]
out=root/'pipeline/UEBA/.build/collector'
out.mkdir(parents=True,exist_ok=True)
shutil.copyfile(root/'pipeline/UEBA/modules/ct-ingest/collector/event_collector.py',out/'event_collector.py')
(out/'pipeline/ueba').mkdir(parents=True,exist_ok=True)
for name in ('pipeline/__init__.py','pipeline/ueba/__init__.py','pipeline/ueba/events.py'):
    shutil.copyfile(root/name,out/name)
print(out)
