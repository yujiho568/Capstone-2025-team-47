> 아래는 ZIP에서 추출한 기존 설명입니다. 이번 개선의 실행 기준은 저장소 루트 docs/LOCAL_DEMO.md와 docs/DEPLOYMENT.md입니다. 새 main은 pipeline/ueba의 공통 전처리·모델 구현을 사용합니다.

# Processing Container (Doc2Vec + OCSVM + DBSCAN)
SageMaker Processing entrypoint. Expects input data (DynamoDB JSON export or Parquet) under
`/opt/ml/processing/input` and writes outputs to:
- `/opt/ml/processing/models/doc2vec/YYYY/MM/DD/model.bin`
- `/opt/ml/processing/models/ocsvm/YYYY/MM/DD/model.joblib`
- `/opt/ml/processing/results/dbscan/YYYY/MM/DD/{stats.json, labels.csv}`
Environment Variables: DATE, GAP_MINUTES, WIN_DOC2VEC, STRIDE_DOC2VEC, VEC_SIZE, WIN_SEG, STRIDE_SEG, MAX_SEQ_PER_SEG, OCSVM_NU, DBSCAN_MIN_SAMPLES, DBSCAN_EPS_PCTL, DBSCAN_K, EVENT_TIME_FIELD, EVENT_NAME_FIELD
