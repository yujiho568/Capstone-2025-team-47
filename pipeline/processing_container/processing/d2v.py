from gensim.models.doc2vec import Doc2Vec, TaggedDocument
def train_doc2vec(corpus_seqs, vec_size=64, window=20, epochs=30):
    docs = [TaggedDocument(words=seq, tags=[str(i)]) for i, seq in enumerate(corpus_seqs)]
    model = Doc2Vec(vector_size=vec_size, window=window, dm=1, min_count=1, negative=5, workers=1, epochs=epochs)
    model.build_vocab(docs)
    model.train(docs, total_examples=len(docs), epochs=epochs)
    return model
def infer_batch(model, seqs, epochs=30):
    return [model.infer_vector(seq, epochs=epochs) for seq in seqs]
