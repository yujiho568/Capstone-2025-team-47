# 이번 로컬 개선 기록 (2026-10-30, 한국 시간)

원본 기준: `pnucse-capstone2025/Capstone-2025-team-47`의
`b56107ea06d1fe1e7c0801f3402fe008a72b7ff7`. 아래 개선을 졸업과제 당시 구현했다고 설명하면 안 된다.
실제 AWS 배포·성능 비교·탐지 정확도 평가는 실행하지 않았다.

## 작업 위치와 소스 기준

기존 `/workspace/Capstone-2025-team-47`은 템플릿 상태였으며 수정하지 않았다.
참고 저장소를 `/workspace/ueba-project`에 읽기 전용 복제한 뒤
`improvement/pipeline-reliability` 브랜치에서 로컬 수정했다. `origin`은
`yujiho568/Capstone-2025-team-47`, `upstream`은 참고 원본이며 upstream push URL은
`DISABLED`다. 최초 구현·검증 단계에서는 어느 저장소에도 push하지 않았다. 이후 사용자가 개인 저장소의 별도 브랜치에 커밋·push하도록 요청하여 `origin`을 업로드 대상으로 사용한다. 이것은 **GitHub상의 fork 생성 완료를 의미하지 않는다**.
GitHub API 요청이 Forbidden으로 거부되어 실제 fork 관계 확인/생성은 미완료다.
후속 지시에서 별도 fork 생성은 필수가 아니라고 정리되었다. 기존 개인 저장소의 `main`을 덮어쓰지 않고 개선 브랜치로 업로드한다.

| 용도 | 실행·배포 기준 | 원본과의 구분 |
|---|---|---|
| 웹 API | `backend/app`, `backend/app/main.py` | 기존 일반 소스를 수정 |
| 웹 화면 | `frontend/src`, Vite | 기존 일반 소스를 수정 |
| 수집 | `pipeline/UEBA/modules/ct-ingest/collector/event_collector.py` → `pipeline/ueba/events.py` | 내부 ZIP을 풀고 공통 구현으로 변경 |
| 실시간 탐지 | `pipeline/realtime_container/lambda_realtime_handler.py` → `pipeline/ueba` | 기존 ZIP을 풀고 변경 |
| 학습 | `pipeline/processing_container/processing/main.py` → `pipeline/ueba/models.py` | 기존 ZIP의 알고리즘 계열을 유지하고 전처리 통일 |
| IaC | `pipeline/UEBA` | 원본 ZIP의 Terraform을 풀고 수정 |
| 원본 보관 | `archive/original/*.zip`, `archive/manifest.json` | 배포 입력 아님; 웹 public에서 제거 |

`processing_container.zip` 안의 이중 `processing_container/processing_container` 복사본과
내장 `.build/*.zip`, remediation ZIP은 기준 소스에서 제외했다. 전체 ZIP 엔트리의
해시를 manifest에 보존했다. 새 수집 ZIP은 `tools/package_collector.py`로 일반 소스에서
스테이징하고 Terraform archive provider로 만든다. 컨테이너는 **저장소 루트**를 빌드 context로 쓴다.
기존 `d2v.py`, `preprocess.py`, `ocsvm.py`, `dbscan_auto.py`는 이전 구현 비교용이며 새 main이 호출하지 않는다.

## 기존 구현 → 이번 변경

| 영역 | 확인한 기존 구현 | 이번 변경 |
|---|---|---|
| 수집 실패 | 모든 저장 예외를 잡고 statusCode 500 반환 | 조건부 중복만 정상 처리; 다른 저장 예외 전파 |
| 잘못된 입력 | 로그와 400 반환 | 원본+오류 종류를 S3 invalid 경로에 보관; 보관 실패도 예외 |
| 이벤트 키 | 사용자명+발생 timestamp, 무조건 put | actor 계정+principal 범위, 시간+eventID 정렬키; 계정+eventID marker와 원자 트랜잭션 |
| 보관 | TTL 없음 | 별도 숫자 expiresAt, 기본 수집 이후 90일; 원본 CloudTrail은 별도 보존 |
| Streams | 첫 레코드만 처리 | INSERT만, marker/MODIFY/REMOVE 무시, 부분 실패 응답과 유한 재시도 |
| 결과 | 알림 먼저, 현재 초 단위 S3 키 | 불변 eventID+modelVersion 키, 결과 먼저 저장, 알림 후 발행(기본 off) |
| 모델 | 각 모델의 최신 날짜를 따로 선택, 캐시 무기한 | 한 버전 manifest로 모델·스케일러·정책·차원·라이브러리 버전·SHA256 연결 |
| 학습 | 사용자 열을 버리고 전체를 시간순 연결 | 사용자·세션별 창 구성; 사용자 경계 넘는 20개 창 금지 |
| 가입 | 루트 키 필수, 요청 model/dump 출력 | 웹 가입과 AWS 연결 분리, 루트 키 거부, 입력 로그 제거 |
| 권한 | import/store/check 일부 무인증 | 모든 대상 경로 소유권 검사; 서버 운영자의 source binding만 사용 |
| 비밀 저장 | 키 부재/복호화 실패 시 평문 fallback | 암호화 키 필수, 전체 credential envelope 암호화, session token+만료 지원 |
| 동기화 | 모든 IntegrityError를 중복으로 처리, 파일별 commit | 고유 충돌 후 실제 기존 소유자·내용 확인, 페이지별 transaction+savepoint |
| UI | 버킷·사용자 하드코딩, require, savedName 미정의 | 서버 binding, ESM, 마지막 동기화와 부분 실패 표시, 최대 100개 페이지 |

## 수집·키·보관의 범위

- pk=`USER#sha256(accountId:principalId)`, sk=`UTC 마이크로초 표기 발생시각#eventID`.
  eventID 동시각 tie를 결정하며 실제 발생 순서를 복원했다는 뜻은 아니다.
- 같은 테이블의 pk=`EVENT#accountId#eventID`, sk=`DEDUP` marker와 행동 row를
  `TransactWriteItems`의 조건부 Put 두 개로 함께 생성한다. 먼저 조회해서 put하지 않는다.
  다른 principal/time으로 재전달돼도 동일 계정/eventID marker가 막는다.
  DynamoDB TransactionConflict/권한/스로틀 등은 중복으로 간주하지 않고 실패시킨다.
- 웹 userId와 CloudTrail userId는 다른 식별자다. assumed-role은 principalId의 session suffix를
  포함한다. 여러 role session을 동일 사용자로 합치는 별도 신원 정규화는 구현하지 않았다.
  Terraform EventBridge 수집 규칙은 명시한 **IAM userName** 범위이며 전체 역할 활동 수집으로 주장하지 않는다.
- timestamp는 발생 시각. DB의 `writeRequestedAt`은 요청 직전 시각이고 저장 완료 시각이 아니다.
  `storedAt`은 DynamoDB 트랜잭션 성공 응답 **후** 수집한 receipt/구조화 로그 시각이다.
  로그는 완료 시각·eventID만 포함하고 자격증명/원본을 출력하지 않는다.
- expiresAt은 수집 수락 시각+보관일수의 Unix 초 숫자다. TTL의 삭제는 비동기이며 즉시가 아니고,
  접근 통제/보안 경계가 아니다. 삭제 전 만료 row가 조회/내보내기에 남을 수 있다.
- 중복 억제는 marker가 남아 있는 보관 기간의 범위다. 90일 이후 재처리를 영구 중복 방지라고
  주장하지 않는다. marker만 먼저 TTL 삭제되고 row가 남은 경우 두 번째 조건 실패를 정상 중복으로 숨기지 않는다.
- 운영 TTL은 90~365일. 실패 S3는 현재·이전 버전 365일, 두 SQS는 14일.
  원본 CloudTrail 버킷 및 모델/학습 export 버킷에는 이번 변경에서 자동 만료를 추가하지 않았다.
  90일 안에 학습/export·복구하고, 더 긴 재처리는 원본 CloudTrail과 보존된 모델로 준비한다.

## 실패 경로와 복구

| 실패 | 재시도 | 원본 보관·복구 |
|---|---|---|
| EventBridge가 대상 Lambda에 전달 실패 | 최대 6회, 최대 나이 3,600초 | delivery_failures SQS, 원래 EventBridge body. 실행 실패와 구분 |
| Lambda가 수락 후 저장/보관 중 실패 | 함수 오류 최대 2회, 이벤트 최대 나이 21,600초 | execution_failures SQS의 requestPayload를 포함한 비동기 invocation record |
| 잘못된 입력 | 보관 성공 후 정상 종료해 재시도 소모 안 함 | S3 invalid/SHA256.json에 원본과 오류 종류. 값 상세는 원본을 권한 있는 운영자가 검토 |
| 탐지 Streams 실패 | 최대 3회, 최대 나이 3,600초, bisect 및 ReportBatchItemFailures | S3 stream_failures에 전체 invocation payload; 메타데이터만 남기는 SQS와 구별 |

이 값은 서비스 내부 backoff, destination 자체 장애까지 포함한 절대 호출 횟수 보장이 아니다.
SQS 비동기 목적지 레코드는 원본+실행 메타데이터 때문에 목적지 메시지 크기 제한에 걸릴 수 있다.
CloudTrail 원본 버킷을 별도 보존하고 `DestinationDeliveryFailures`, `DeadLetterErrors`,
Lambda Errors/Throttles, Streams IteratorAge와 DLQ oldest age를 운영 경보에 연결해야 한다.
이번 작업은 경보의 실제 배포나 발송을 검증하지 않았다.

1. 원본 AWS 자원은 삭제하지 않고 실패 큐/S3 객체를 접근 통제된 로컬 경로로 내려받는다.
2. `python tools/replay.py failure.json --output reviewed-replay.jsonl`로 envelope를 푼다.
   AWS API를 호출하거나 메시지를 삭제하지 않는다. 변환에 실패하면 누락된 원본을 CloudTrail에서 복구한다.
3. 원인(권한·모델·스로틀·형식)을 수정한 뒤 사람이 검토한다. invalid 원본에서 eventID를 임의 생성하지 않는다.
4. 검토한 **한 이벤트** JSON을 운영자가 `aws lambda invoke --function-name <collector-or-detector>
   --cli-binary-format raw-in-base64-out --payload file://reviewed-event.json response.json`로 재호출한다.
   JSONL 파일 전체를 한 invocation에 보내지 않는다. 응답의 FunctionError/부분 실패와 실제 결과 저장을 확인한다.
5. 확인 후에만 원본 실패 보관물/큐 메시지를 운영 보관 정책에 따라 처리한다. 도구는 자동 삭제하지 않는다.

DynamoDB Streams는 24시간 보존이므로 장애 이후 무기한 기다리지 않는다. S3 원본 invocation에는
event row가 있어도 history가 이미 TTL로 사라졌으면 당시 입력을 재구성할 수 없다. CloudTrail/export와
당시 모델을 별도로 복원한 환경에서 재처리해야 한다.

## 테이블·웹 DB 이관

기존 `user_event_buffer`의 키나 이름을 바꾸지 않고 별도 `events_v2`를 추가했다.
legacy 테이블과 v2는 prevent_destroy, v2는 deletion protection/PITR를 켠다.
기존 Terraform state와 **기존 monitored username을 동일하게** 연결해야 한다. 이름을 바꾸면
다른 자원 생성/교체가 계획될 수 있으므로 plan의 destroy/replace를 검토하고 중단한다.
자동 apply/destroy/data 삭제는 실행하지 않았다.

이관 순서: 기존 테이블 백업·상태 백업 → v2 준비 → 같은 시간 구간의 원본 CloudTrail 로그 확보 →
`tools/backfill_cloudtrail.py downloaded.json.gz --output backfill.jsonl`로 원래 eventID를 가진 입력 준비 →
조건부 수집기로 유한 배치 재생 → 계정/eventID별 수·동시각 row·누락 비교 → 수집 및 탐지 source 전환.
과거 table은 userName/timestamp/eventName만 있어 원래 eventID를 복구할 수 없다. 이미 덮어쓴 이벤트를
그 테이블만으로 복원했다고 주장하면 안 된다. EventBridge 수집을 전환하는 동안 원본 로그로 gap을
보충하고 이전 테이블은 별도 승인된 보관기간까지 읽기 전용 유지한다.

웹 DB의 기존 users AWS 키 열은 데이터를 파괴하지 않기 위해 남겼지만 활성 API는 사용하지 않는다.
기존 plaintext credential은 복호화 fallback 없이 거부한다. 안전한 DB 백업 후 과거 루트/장기 키를
회전·폐기하고 제한된 새 IAM/임시 credential을 별도로 재등록한다. 예전 DB를 새 암호화 키로 조용히
재사용하지 않는다. 새로운 `result_sources` 테이블만 create_all로 추가하며 기존 열 삭제는 없다.
등록된 source는 `tools/bind_source.py`의 dry-run을 검토한 운영자가 --write로 연결한다.
버킷 전체나 다른 사용자의 prefix를 브라우저가 선택할 수 없다. 격리 API는 501이며 실제 IAM 차단을
복구하려면 제한 역할·소유 대상 binding·승인/감사 설계가 추가로 필요하다.

## 세션·모델 정책과 한계

기존 README는 초기 세션을 '로그인 후 30분 이내 또는 세션 단절 후'라고 기술한다.
기존 학습 코드는 30분 이상 인접 gap을 세션 경계로 두고, 세션 처음부터 창 길이 20,
stride 5, 최대 5개를 OCSVM 학습에 썼다. 실시간 ZIP은 (20,21)/(25,26)/(30,31)의 gap이
30분 이상이면서 최근 이벤트와 **더 오래된 쪽**의 차이가 30분 이하인지를 검사한다.
시간순이면 더 오래된 쪽→최근의 차이는 경계 gap 이상이므로, 일반적인 여러 시각의 데이터에서
이 조건은 성립하기 어렵고 정확히 같은 경계 시각 같은 예외만 가능하다. n<2 반환 False와
'초기 세션으로 간주'라는 주석도 불일치했다. 문서와 코드가 동일했다고 간주하지 않았다.

**이번에 선택한 정책**은 실제 학습 창 생성에 맞춘 명시적 정책이다. 인접 gap >=30분으로
사용자별 세션을 나누고, 그 세션 내 최근 20개만 사용한다. endpoint 20,25,30,35,40은
OCSVM 초기 창, 나머지는 DBSCAN 창이다. '30분 이내의 모든 활동이 초기 창'이라는 정책과 다르다.
20개 미만이면 insufficient_history이고 정상/위험 판정을 생성하지 않는다. OCSVM/DBSCAN과
nu=.05, cosine 거리/자동 eps, 문서 벡터 64차원 운영 기본을 유지했다.
초기 정책 변경과 데이터 분리 효과의 탐지 정확도·운영 임계값은 재학습 후 따로 평가해야 한다.

학습/추론은 같은 정렬(timestamp,eventID), gap, window, Doc2Vec infer 100 epochs를 쓴다.
학습·스케일러·추론 전체가 같은 manifest 버전/정책/라이브러리 버전/차원/파일 SHA를 확인한다.
모델 다운로드 실패·불일치·DBSCAN core 없음은 운영 오류이며 risk=100이나 정상 결과로 바꾸지 않는다.
실시간 query는 최대41개만 읽는다. 40번째 이후에는 초기 창이 될 수 없고 마지막20개와
그 안의 세션 경계만 필요하므로 긴 세션 전체를 읽지 않는다.

joblib은 실행 가능한 형식이므로 신뢰된 학습 역할만 모델 경로에 쓸 수 있어야 한다. checksum은
권한 있는 공격자가 manifest까지 바꾸는 것을 막는 서명이 아니다.

Lambda는 MODEL_VERSION 고정 버전을 cold start에 로드하고 동일 버전은 재사용한다. 새 파일을
같은 버전 아래 덮어써도 warm 인스턴스가 새로 읽지 않는다. 새 immutable bundle 이름으로 발행하고,
MODEL_VERSION 설정을 바꿔 새 환경으로 전환한다. 혼재 배포 기간에는 두 버전 결과가 공존할 수 있다.

결과 경로는 `results/realtime/<principal hash>/<modelVersion>/<account+eventID hash>.json`이고
IfNoneMatch 조건부 쓰기로 기존 결과를 덮어쓰지 않는다. 기존 결과가 있으면 그 결과로 알림을 재시도한다.
같은 eventID+모델의 **최초 성공 결과를 고정**하는 정책이다. 늦게 도착한 과거 이벤트 때문에 history가
달라져도 기존 결과를 재계산하지 않는다. Streams는 사용자 전체 시간순 정렬 장치가 아니며 다른 shard의
역순 도착/지연을 자동 보정하지 않는다. 별도 backfill 분석은 새 분석/모델 버전으로 관리해야 한다.

결과 저장 실패: 알림을 보내지 않는다. 결과 저장 후 알림 실패: 재시도에서 기존 결과를 읽고 알림 재발행.
알림 성공 후 응답 유실: 동일 resultKey 알림이 중복될 수 있다. 외부 consumer의 원자적 중복 억제/outbox는
이번 작업에 포함하지 않았다. EMIT_ANOMALIES 기본 false, 기존 remediation rule도 DISABLED이고
기존 광범위 IAM 쓰기 권한은 제거했다. risk는 모델 거리/결정함수의 0~100 지표이며 공격 확률이 아니다.

## S3 동기화 계약

- source binding의 버킷·prefix·principal만 사용하고 payload.userId도 일치해야 한다.
- 단일 페이지 최대 1,000개(기본100), 객체 최대1MiB, timeout과 SDK 시도 횟수를 제한한다.
  페이지별 한 commit, 객체별 savepoint로 유효 파일은 보관하고 잘못된 파일은 failures에 기록한다.
- 같은 bucket+key+동일 canonical JSON이면 duplicate. 동일 key의 내용 변경은 immutable_object_changed.
  S3 VersionId 업데이트 수집은 지원하지 않는다. 새 결과는 반드시 새 키/모델 버전으로 발행한다.
- 다른 IntegrityError는 중복으로 처리하지 않는다. DB flush/commit 또는 list 연결 실패는 요청 자체를
  503으로 실패시키고 '정상/빈 결과'로 반환하지 않는다. 페이지 도중 get 실패는 부분 실패로 표시한다.
- JSON 문법, timezone, 필수 필드, strict bool/int, engine별 필드, 유한한 위험 점수0~100을 검증한다.
- scanned/imported/skipped_existing/errors/failures/status/synced_at/continuation_token 반환.
  partial_failure이면 continuation을 전진시키지 않는다. 같은 페이지 재시도로 실패를 복구한다.
- continuation은 UI 세션의 메모리 값이다. 새 객체가 이전 사전식 위치에 삽입될 수 있어 영구 high-water
  mark로 쓰면 안 된다. 전체 날짜 인덱스/영구 cursor는 미구현이며 정기적으로 처음 페이지부터
  제한된 범위를 재스캔해야 한다. 변경 감지를 위해 기존 객체 body도 다시 읽으므로 비용이 남는다.
  frontend는 전체를 무제한 자동 순회하지 않는다. 마지막 동기화 시각은 현재 화면 세션 값이다.

## 실행·검증

[LOCAL_DEMO.md](LOCAL_DEMO.md), [DEPLOYMENT.md](DEPLOYMENT.md),
[validation/RESULTS.md](validation/RESULTS.md)를 따른다. 원본 README는 역사 기록으로 유지하며
아래 파일들이 **이번 변경 이후의 실행 지침**이다. 원본의 destroy/apply 재시도 절차는 사용하지 않는다.

학습 상태 출력과 summarize를 `results/training/<jobName>/training-status.json`으로 함께 변경했고,
날짜별 덮어쓰기 대신 모델/job 버전별 불변 summary를 기록한다. export prefix에도 UUID를 넣어
같은 날짜의 이전 export를 새 학습 입력에 섞지 않는다. count/summarize ZIP에는 source_code_hash를
연결해 소스 변경이 실제 Lambda 업데이트로 반영되도록 했다. 원본 remediation ZIP의 IAM 쓰기는
주석 처리되어 있었지만 역할에는 광범위 권한이 남아 있었다. 이번에는 권한·rule·handler 모두
명시적으로 비활성화하며 격리 성공처럼 응답하지 않는다.
