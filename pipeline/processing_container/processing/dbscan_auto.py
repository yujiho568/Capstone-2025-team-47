import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.cluster import DBSCAN
def auto_eps_cosine(X, k=10, pctl=90):
    if len(X) == 0:
        return 0.5
    n_neighbors = min(k, max(1, len(X)))
    nn = NearestNeighbors(metric='cosine', n_neighbors=n_neighbors).fit(X)
    dist, _ = nn.kneighbors(X)
    kth = dist[:, -1]
    return float(np.percentile(kth, pctl))
def run_dbscan_cosine(X, min_samples=8, k=10, pctl=90):
    eps = auto_eps_cosine(X, k=k, pctl=pctl)
    if eps <= 0:
        eps = 0.5
    db = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine').fit(X)
    labels = db.labels_.tolist()
    return eps, labels, db
