"""Provenance only: names/checksums, never extract over edited sources."""
import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
report={'upstream_commit':'b56107ea06d1fe1e7c0801f3402fe008a72b7ff7','archives':{}}
for p in sorted((ROOT/'archive/original').glob('*.zip')):
    with zipfile.ZipFile(p) as z:
        report['archives'][p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'files':{i.filename:hashlib.sha256(z.read(i)).hexdigest() for i in z.infolist() if not i.is_dir()}}
print(json.dumps(report,indent=2))
