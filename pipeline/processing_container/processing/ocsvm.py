from sklearn.svm import OneClassSVM
def train_ocsvm(X, nu=0.05):
    clf = OneClassSVM(kernel='rbf', nu=nu, gamma='scale')
    clf.fit(X)
    return clf
