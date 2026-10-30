"""Trusted model bundle: all artifacts and preprocessing share one immutable version."""
import hashlib
import json
import re
from importlib.metadata import version as package_version
from pathlib import Path
import joblib
import numpy as np
from gensim.models.doc2vec import Doc2Vec, TaggedDocument
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors
from .events import windows

DEPENDENCIES={name:package_version(name) for name in ('gensim','numpy','scipy','scikit-learn','joblib')}

POLICY={'window':20,'gap_minutes':30,'initial_endpoints':[20,25,30,35,40],
        'order':['timestamp','eventID'],'infer_epochs':100,'alpha':5.0}

class ModelUnavailable(RuntimeError): pass

def infer_vector(model, tokens):
    # Stable per-sequence seed, also across retries/processes (PYTHONHASHSEED=0).
    model.random.seed(int(hashlib.sha256('\0'.join(tokens).encode()).hexdigest()[:8],16))
    return model.infer_vector(tokens, alpha=.025, min_alpha=.0001, epochs=100)

def train(rows, directory, version, minimum=3000, vec_size=64, min_samples=10):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',version): raise ValueError('invalid_model_version')
    if len(rows)<minimum: return {'status':'skipped','count':len(rows),'minimum':minimum}
    samples=list(windows(rows))
    if not samples or not any(initial for _,initial in samples):
        raise ModelUnavailable('no_complete_session_windows')
    directory=Path(directory)/version
    directory.mkdir(parents=True, exist_ok=False)
    corpus=[[r['eventName'] for r in seq] for seq,_ in samples]
    model=Doc2Vec(vector_size=vec_size,window=20,dm=1,min_count=1,negative=5,workers=1,epochs=30,seed=47)
    docs=[TaggedDocument(s,[str(i)]) for i,s in enumerate(corpus)]
    model.build_vocab(docs); model.train(docs,total_examples=len(docs),epochs=30)
    x=np.asarray([infer_vector(model,s) for s in corpus])
    scaler=StandardScaler().fit(x[[initial for _,initial in samples]])
    oc=OneClassSVM(kernel='rbf',nu=.05,gamma='scale').fit(scaler.transform(x[[i for _,i in samples]]))
    nn=NearestNeighbors(metric='cosine',n_neighbors=min(10,len(x))).fit(x)
    eps=max(float(np.percentile(nn.kneighbors(x)[0][:,-1],90)),1e-6)
    db=DBSCAN(eps=eps,min_samples=min_samples,metric='cosine').fit(x)
    if len(db.components_)==0: raise ModelUnavailable('no_dbscan_core_samples')
    model.save(str(directory/'doc2vec.bin'), separately=[])
    joblib.dump(dict(scaler=scaler,ocsvm=oc,components=db.components_,
                     labels=db.labels_[db.core_sample_indices_],eps=eps), directory/'detectors.joblib')
    manifest=dict(schema_version=1,version=version,policy=POLICY,dependencies=DEPENDENCIES,embedding_dim=vec_size,files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in directory.iterdir() if p.is_file()})
    (directory/'manifest.json').write_text(json.dumps(manifest,sort_keys=True))
    return {'status':'trained','count':len(rows),'windows':len(samples),'version':version}

class Bundle:
    def __init__(self, directory, version):
        root=Path(directory)/version
        try:
            manifest=json.loads((root/'manifest.json').read_text())
            if (manifest.get('schema_version')!=1 or manifest.get('dependencies')!=DEPENDENCIES
                or manifest['version']!=version or manifest['policy']!=POLICY): raise ValueError('policy/version')
            if set(manifest['files'])!={'doc2vec.bin','detectors.joblib'}: raise ValueError('files')
            for name, sha in manifest['files'].items():
                if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha: raise ValueError('checksum')
            self.d2v=Doc2Vec.load(str(root/'doc2vec.bin'))
            self.art=joblib.load(root/'detectors.joblib')
            if self.d2v.vector_size!=manifest['embedding_dim'] or self.art['components'].shape[1]!=self.d2v.vector_size:
                raise ValueError('dimension_mismatch')
            if len(self.art['components'])==0: raise ValueError('empty cores')
        except Exception as exc: raise ModelUnavailable('bundle_missing_or_inconsistent') from exc
        self.version=version

    def predict(self, seq, initial):
        v=infer_vector(self.d2v,[r['eventName'] for r in seq]).reshape(1,-1)
        if initial:
            score=float(self.art['ocsvm'].decision_function(self.art['scaler'].transform(v))[0])
            z=-score
            out=dict(engine='ocsvm',score=score,is_anomaly=score<=0)
        else:
            from sklearn.metrics.pairwise import cosine_distances
            distances=cosine_distances(v,self.art['components'])[0]
            idx=int(np.argmin(distances)); d=float(distances[idx]); eps=float(self.art['eps'])
            z=d/eps-1
            out=dict(engine='dbscan',cluster=int(self.art['labels'][idx]) if d<=eps else -1,
                     is_noise=d>eps,nearest_dist=d,eps=eps,r=d/eps)
        out['risk']=float(100/(1+np.exp(-np.clip(5*z,-60,60))))
        return out
