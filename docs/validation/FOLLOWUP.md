# 후속 기능 검증 기록

기존 검증 문서는 첫 개선의 당시 기록이다. 이 문서는 내용 충돌·큐 복구·재분석·시각 기록 후속 변경의 검증이다.
실제 AWS 자원 생성/삭제/과금/차단/실패 큐 재생은 실행하지 않았다. 아래 수치는 실제 실행한 로컬 로그에서 옮겼다.

| 검사 | 실제 결과 | 범위 |
|---|---|---|
| 전체 pytest | **62 passed**, warnings 10, 24.95초 | Moto/예외 모의/SQLite/FastAPI IPC/실제 ML |
| frontend lint / build | 통과 | 오류/경고0, Vite 모듈56개; 브라우저 자동화 아님 |
| Terraform validate / fmt -check | 통과 | provider schema/문법. plan/apply 및 IAM 실제 강제 아님 |
| 기본 데모 | 입력120, 저장120, 결과82, 조회82 | 새 demo-v2 모델/별도 상태 경로 |
| 복구 데모 | 입력120, 학습119건 | 합성 데이터; 탐지 정확도 평가 아님 |
| 두 큐 형식 복구 | stored, duplicate, 삭제2개 | Moto SQS + 직접 handler 호출 adapter |
| 충돌 입력 | conflict | 원본 보존, 행동 row 덮어쓰지 않음 |
| 영향 구간 재분석 | 20개 | 같은 모델의 전체 시간순 기준 결과와 일치 |
| API 동기화 | imported102/errors0 | realtime82 + reanalysis20 |
| API 조회 | 전체102, 재분석20 | 버전/원본 연결을 응답·raw_json에 보존 |
| 재분석 알림 | 0개 | 발행 client 자체가 없음 |
| 재분석 CLI dry-run/execute/repeat | 통과 | 로컬 파일만 읽기/불변 저장; 동일 실행 결과 재사용 |
| 학습 이미지 빌드 및 network none smoke | 통과 | 비루트 export 로드→영향 결과20개→기존 실제64차원 모델 추론 |
| 실제 Lambda 기반 이미지 | 미검증 | 이전 public.ecr.aws 접근 Forbidden 이후 환경 허용 반영 확인 없음 |
| 실제 AWS 전달 지연/관리형 재시도 | 미실행 | 로컬 결과로 대체 주장하지 않음 |

원본 요약 JSON: [기본 데모](followup/basic-demo.json), [복구 데모](followup/recovery-demo.json),
[로컬 시각 측정](followup/local-latency.json).
기본 데모는 `.demo/basic-followup`, 복구 데모는 `.demo/recovery/final`에서 실행해 이전 상태를 보존했다.

## 추가한 테스트의 핵심

- 같은 계정/eventID·같은 내용/다른 내용의 동시 입력, 전달 메타데이터 및 JSON 키 순서/timezone 변화.
- legacy marker, 보관기간 만료, marker 조회 실패/TTL 경쟁, 행동 기록 누락, 충돌 보관 실패.
- 트랜잭션 두 번째 조건 실패 시 첫 marker도 생성되지 않음.
- 두 SQS envelope 및 Messages 배열, malformed/missing original, depth/target/visibility/처리 상한.
- dry-run에서 SDK client/호출/삭제 없음, HTTP200+FunctionError, invalid/conflict/다른eventID/구형 응답은 삭제 안 함.
- 저장 성공 후 응답 유실, 같은 입력의 두 worker, receive 상한, 시간 예산, 배치 삭제의 개별 실패.
- 실제 Doc2Vec/OCSVM/DBSCAN으로 지연 이벤트 복구 결과와 시간순 기준 입력 비교.
- 30분 세션 합침/초기 창 변경, 영향 결과 상한, 만료/불완전/위조 checksum/혼합 사용자 이력 거부.
- 모델 버전과 분석 버전 구분, 불변 plan/결과, 부분 run 완료 미발행, resume, legacy 입력 이력 누락 거부.
- 짧은 입력은 분석 실패/보류로 구분하고, 변경 없는 재실행은 no_change이며 결과를 생성하지 않음.
- 완료 전 웹 DB 적재 거부, 완료 후 모델/분석 버전/원본 연결 조회, 현재 경보로 과거 결과 발행 차단.
- 실제 handler 진입 시각 및 DB 전후 시각, 확보되지 않은 CloudWatch 구간은 null, 음수 시각 차이 표시.

경고는 passlib/crypt, Starlette/python-multipart, httpx TestClient의 deprecated 인터페이스 등이다.
경고를 무시해 통과로 바꾸거나 테스트를 비활성화하지 않았다.

## 시각 측정

현재 시각으로 이벤트30개씩 실제3회, 총90개를 실행했다. 리소스 생성과 회차별 warmup1개는 제외했다.
이 측정은 local Moto의 serial 처리이며, AWS eventTime→CloudWatch 수신→프로그램 조회 구간을 포함하지 않는다.
단일 호스트 시각 차이의 소수점 표시를 CloudTrail의 밀리초 정확도라고 주장하지 않는다.

| 회차 | 건수 | 평균(초) | 중앙값(초) | p95(초) | 최대(초) |
|---|---:|---:|---:|---:|---:|
|1|30|0.009279|0.007345|0.011940|0.077162|
|2|30|0.019061|0.015960|0.022320|0.118896|
|3|30|0.030242|0.025014|0.029815|0.184649|

로컬 도구에서 실제 Lambda handler를 호출하지 않았기 때문에 handler 구간 samples=0이며,
CloudWatch ingestion/read 구간도 samples=0/statistics=null이다. 값을0초로 채우지 않았다.
복구 데모에서는 실제 handler 함수를 직접 실행해 handlerEnteredAt 기록 유무를 별도로 검증했다.
복구 데모의 고정된 과거 합성 발생 시각을 현재 저장 시각과 빼서 AWS 지연으로 사용하지 않았다.

## 남은 범위

snapshot 완전성은 원본 archive에 대한 외부 검토 근거가 필요하다. 해시만으로 누락 없는 수집을 증명하지 않는다.
상시 복구 worker/스케줄, 자동 지연 감지/재분석, 알림 consumer 중복 억제/outbox, 차량 현재 상태 갱신은 없다.
실제 AWS IAM·SQS visibility/중복·Streams checkpoint/TTL/S3 조건부 동시성·quota/성능은 추가 통합 검증이 필요하다.
