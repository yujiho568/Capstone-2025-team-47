# AWS 없이 재현하기

저장소 루트에서 실행한다. Python 3.11, Node 24(이번 검증: 24.19.0), uv를 사용한다.
실제 AWS 자격증명·AWS 자원·Docker 없이 기본 데모를 실행할 수 있다.
`uv`를 설치해야 한다면 공식 배포 지침과 조직의 인증서 정책을 따른다.

```bash
cd /workspace/ueba-project
uv python install 3.11
uv venv --python 3.11 .venv311
uv pip sync --python .venv311/bin/python requirements.lock
PYTHONHASHSEED=0 .venv311/bin/python -m pytest -q
PYTHONHASHSEED=0 .venv311/bin/python tools/demo.py run
```

`run`은 Moto 컨텍스트에서 **합성 이벤트 → 수집 코드 → DynamoDB 트랜잭션 →
사용자별 세션/20개 행동 창 → 실제 gensim Doc2Vec 학습/추론 + 실제 sklearn OCSVM/DBSCAN →
S3 JSON → 인증된 FastAPI 가져오기 → SQLite → 결과 조회**를 수행한 뒤 종료한다.
첫 실행은 모델도 준비하므로 별도 사전 학습 파일이 필요 없다. `.demo/report.json`,
`.demo/results`, `.demo/web.sqlite`, `.demo/models`를 생성한다. stdout에는 테스트 결과만 출력한다.
`.demo/app-keys.json`은 매 로컬 상태별 생성한 앱 서명/암호화 키(0600)이며 Git에서 제외된다.

데모 데이터는 120건, 두 세션, 16차원, 최소 학습100건, DBSCAN min_samples3의
**연결 검증용 설정**이다. 운영 기본64차원/최소3,000건/min_samples10과 분리했다.
기존 모델 없이 외부 runtime handler만 실행하면 model_missing_or_inconsistent 오류가 나며,
정상이나 고위험 판정으로 대체하지 않는다. 데모에서는 `reset` 후 `run`으로 새 모델을 준비한다.
임의의 오래된/손상된 모델을 그대로 덮어쓰지 않는다.

재실행은 같은 모델을 재사용하고 기존 웹 DB 결과를 중복으로 처리한다.
Moto 자원은 매 프로세스 새로 만들어지므로, 재실행 결과가 실제 AWS 자원의 영속성을 증명하지는 않는다.
새 모델 bundle manifest 형식이 변경되었다면 데모를 중지하고 reset 후 다시 학습한다.

## 웹 서버와 화면

```bash
# 터미널 1: seed 후 Moto를 유지하며 FastAPI를 실행
PYTHONHASHSEED=0 .venv311/bin/python tools/demo.py serve
# 터미널 2
cd frontend
npm ci
npm run dev
```

테스트 계정은 `demo@example.com` / `local-demo-only-47`이다. 가짜 AWS credential `demo`와
테스트 principal의 source binding은 데모 스크립트가 만들어 준다. 실제 AWS 키를 입력하지 않는다.
UI 로그인 후 Dashboard와 Results에서 조회하고 동기화할 수 있다.
서버의 health 및 실제 HTTP 로그인·82개 결과 조회를 검증했다. 브라우저 자동화 검증은 하지 않았다.

종료: 두 터미널에서 각각 `Ctrl-C`. 종료 후 아래 명령으로 생성된 `.demo`만 초기화한다.
프로세스가 살아 있을 때 reset하지 않는다. 코드·원본 ZIP·실제 AWS 데이터는 삭제하지 않는다.

```bash
.venv311/bin/python tools/demo.py reset
```

`tools/demo.py serve`를 켜 둔 채 `uvicorn app.main:app`을 별도로 띄우면 Moto가 공유되지 않는다.
데모용 server는 반드시 제공한 serve 명령을 사용한다.

## 별도 합성 입력/실패 복구/시간 도구

```bash
.venv311/bin/python tools/synthetic.py --count 120 > /tmp/synthetic-events.jsonl
.venv311/bin/python tools/replay.py /path/to/downloaded-failure.json --output /tmp/reviewed-replay.jsonl
.venv311/bin/python tools/backfill_cloudtrail.py /path/to/downloaded-log.json.gz --output /tmp/backfill.jsonl
```

위 명령은 실제 AWS에 전송하지 않는다. 이미 존재하는 replay output을 덮어쓰지 않는다.
파일이 잘못되면 중단하고 원본을 검토한다. 부분 생성된 output을 완성된 replay로 사용하지 않는다.

```bash
.venv311/bin/python tools/latency.py \
  --events /path/to/actual-original-events.jsonl \
  --receipts /path/to/actual-path-a-receipts.jsonl /path/to/actual-path-b-receipts.jsonl
```

eventID로 대응해 평균·중앙값·nearest-rank p95·최대(초), 누락/중복/예상 외 이벤트,
음수 지연(시계 문제)·실제 건수·입력 receipt 파일 개수를 반환한다. 각 파일은 실제 별도 측정 path/run이어야
한다. 동일 파일 복사본을 반복 측정으로 세지 않는다. 수집 Lambda의 storedAt receipt 구조화 로그를 추출해 쓴다.
발생 timestamp가 초 단위면 밀리초 정확도를 주장할 수 없다.
`.demo`는 고정된 과거의 합성 발생 시각을 쓰므로 latency.py로 계산해도 AWS 수집 지연 측정이 아니다.
**실제 AWS 경로 비교 지연은 미측정**이다. 문서에 목표 수치/대화 속 숫자를 측정값으로 넣지 않았다.

## 모의 구간과 남은 차이

Moto가 DynamoDB/S3/STS API를 메모리에서 흉내 낸다. EventBridge의 전송, Lambda 관리형 비동기
재시도, 실제 Streams 전달/checkpoint/TTL 삭제, IAM 권한 강제, S3 원자 조건부 쓰기의 실제 서비스
동시성, AWS quota·성능은 이 데모가 재현하지 않는다. Streams 레코드 유형과 부분 실패 응답은
별도 테스트로 검증했다. 알림 발행 오류는 모의 실패 테스트, 실제 알림과 IAM 차단은 실행하지 않았다.
정확도 평가용 데이터/레이블/통계적 검증은 별도 작업이다.
