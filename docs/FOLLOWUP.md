# 질의응답 이후 추가한 개선

이 문서는 `fd51ea6`의 첫 개선과 개인 main의 병합 `585b56a` 이후 추가한 작업이다.
이전 구현·측정 기록은 역사 기록으로 보존한다. 아래 기능을 졸업과제 당시 구현했다고 설명하지 않는다.
개인 저장소 `yujiho568/Capstone-2025-team-47`의 main 반영을 위한 작업이며,
새 커밋 작성자는 `유지호 <yujiho568@gmail.com>`이다. 참고 원본에는 쓰기 작업을 하지 않는다.

## 1. 동일 ID의 재전달과 내용 충돌

첫 개선은 계정/eventID만 같으면 중복으로 종료했다. 이제 다음을 구분한다.

- 해시 정책 `cloudtrail-detail-v1`: **CloudTrail detail 전체**를 JSON 키 순서와 무관하게 직렬화하고
  eventTime은 UTC 마이크로초 표기로 정규화한 뒤 SHA256을 계산한다.
- EventBridge의 top-level id/time/resources 등 전달용 메타데이터는 비교 대상에서 제외한다.
  detail 안의 사용자·발생 시각·작업명·requestParameters 등은 비교 대상이다.
- marker에 `contentHash`, `hashPolicy`, 실제 행동 기록의 `eventPk`/`eventSk`, expiresAt을 저장한다.
  marker와 행동 row는 계속 조건부 트랜잭션으로 함께 저장한다. 선조회 후 put 방식이 아니다.
- 조건 실패 후 marker를 ConsistentRead로 읽고, 해시·보관기간·행동 기록 존재/주요 필드도 확인한다.
  일치할 때만 duplicate다. hash mismatch는 conflict로 분류하고 원본/사유/비교 해시를 S3 conflicts에 보관한다.
- legacy/알 수 없는 해시 정책, 포인터 없는 marker, 만료 marker, 행동 row 누락·불일치는 정상 중복으로
  숨기지 않고 검토 대상으로 보관한다. 조건 실패 후 marker가 사라지는 TTL 경쟁은 예외로 재시도한다.
- conflict 보관 실패, marker/행동 조회 실패, TransactionConflict/스로틀/권한/불명확한 취소는 예외를 전달한다.
  다른 장애 사유가 섞인 트랜잭션 취소를 중복으로 간주하지 않는다.
- 같은 내용의 JSON 키 순서 변화와 동등한 timezone 표기는 허용하지만, 없는 필드와 null 같은 의미 차이를
  서비스별로 추정하지 않는다. 향후 정규화 정책 변경 시 해시 정책 버전을 올리고 이관을 검토해야 한다.

legacy marker를 현재 들어온 이벤트 내용으로 자동 보충하지 않는다. 백업/원본 CloudTrail 및 기존 row.rawEvent로
원래 내용을 검토한 뒤 별도 이관해야 한다. 오래된 TTL 데이터의 재수집을 위해 marker를 무작정 삭제하지 않는다.
원본을 다른 복원 환경에 준비하고 분석 버전을 분리하는 방식이 필요하다.

구현: `pipeline/ueba/events.py`, collector handler, ct-ingest Terraform.
collector는 실제 handler 첫 줄의 `handlerEnteredAt`을 receipt에 넣으며 SDK timeout/시도 횟수를 제한한다.
이 시각은 runtime 전달·cold start 이후의 Python 함수 진입 시각이다. 네트워크 도착 시각으로 해석하지 않는다.

## 2. 두 실패 큐의 제한된 복구 worker

`tools/replay.py`의 기본 동작은 **로컬 파일 추출·검증**이다. AWS client를 만들지 않는다.

```bash
.venv311/bin/python tools/replay.py downloaded-message.json --output /tmp/reviewed-events.jsonl
```

단일 메시지와 `{ "Messages": [...] }` 배열을 지원한다. EventBridge 전달 실패의 Body는 원래 이벤트이고,
Lambda 실행 실패의 Body는 invocation record이므로 requestPayload를 추출한다. 최대100개 이벤트,
envelope 깊이8, 메시지1MiB/입력 파일20MiB 상한을 적용한다. Streams 실패 입력은 오프라인 추출할 수 있지만
수집 Lambda worker의 입력으로는 거부한다. JSONL은 검토용이며 통째로 한 invocation에 넣지 않는다.

**실제 큐 복구는 이번 작업에서 실행하지 않았다.** 다음은 운영자가 명시적으로 실행할 수 있는 경로다.
설정의 큐 URL/Lambda ARN을 실제 배포 출력과 대조하고, 같은 계정·리전의 한 대상을 지정한다.
메시지에서 호출 대상이나 버킷을 읽어 오지 않는다. 예제의123456789012는 가짜 계정이다.

```bash
# examples/replay-config.json을 별도 파일로 복사하고 실제 검토한 대상만 지정한다.
.venv311/bin/python tools/replay.py --config /secure/replay-config.json --receive --execute
# 성공 확인된 메시지를 삭제하는 것까지 별도로 허용할 경우에만:
.venv311/bin/python tools/replay.py --config /secure/replay-config.json --receive --execute --delete-success
```

- 최대 처리100개/실행3,600초, 기본10개/300초. 한 receive는 최대10개이고 장기 polling 서비스가 아니다.
- SDK invoke는 명시적 단일 시도, connect5초/read기본65초. 이미 저장된 뒤 응답이 유실될 수 있으므로
  invoke timeout만 보고 새 이벤트를 만들어 다시 보내지 않는다. 원래 eventID로 재처리한다.
- visibility는 일괄 수신한 메시지의 순차 처리 최악 시간+여유를 덮도록 검증하고, 호출 직전 갱신한다.
  기본900초. SQS 표준 큐의 중복 전달을 배제하지 않으며 저장 멱등성으로 대응한다.
- 기본 ApproximateReceiveCount5회 초과는 삭제하지 않고 검토 대상으로 남긴다. 만료 전 운영 보관이 필요하다.
- HTTP200뿐 아니라 FunctionError 부재, 함수의 stored/duplicate 상태, eventID, **해시 정책과 내용 해시**를
  확인해야 성공으로 본다. 과거 collector의 단순 duplicate 응답은 자동 삭제하지 않는다.
- invalid/conflict·형식 오류·invoke 오류·응답 유실·시간 예산 소진은 삭제하지 않는다.
- --delete-success를 줬을 때만 확인된 성공을 배치 삭제하며, 삭제 API의 Successful/Failed 항목을 따로 검사한다.
  삭제 응답을 확인하지 못하면 deleted로 보고하지 않는다. 재실행은 동일 이벤트를 다시 검증한다.
- 시간 상한은 각 요청 시작 전 검사한다. 진행 중 요청은 SDK timeout까지 걸릴 수 있다. 강제 취소를 보장하지 않는다.
- Terraform recovery_operator 정책은 두 큐와 collector 호출에 제한하며 자동으로 어떤 역할에도 붙이지 않는다.
  별도 검토 후 운영자 역할에 연결해야 한다. 상시 worker·스케줄·자동 DLQ redrive는 배포하지 않았다.

## 3. 지연 이벤트의 제한된 과거 재분석

새 이벤트의 시간순 조회만으로 이미 계산된 결과가 바로잡히지는 않는다.
`pipeline/ueba/reanalysis.py`와 `tools/reanalyze.py`를 추가했다.

입력은 **지연 이벤트가 들어오기 전의 완전한 세션 스냅샷**과 복구한 원본 이벤트다.
필수 스냅샷에는 coverageStart/End, eventCount, eventsSha256, source, completenessEvidence,
sessionBoundariesVerified와 모델 입력용 이벤트·expiresAt이 들어간다.
`make_snapshot`은 파일 준비 도구이고 완전성을 자동 증명하는 기능이 아니다.
source는 reviewed-archive 또는 synthetic-fixture이며, 실제 archive의 누락 여부와 세션 경계는
운영자가 원본/export 기록으로 독립 검토해야 한다. 체크섬 일치만으로 완전한 CloudTrail 이력이라고 주장하지 않는다.
검토 근거가 없거나, 데이터가 만료됐거나, 일부 이벤트/체크섬/소유 범위가 불일치하면 재분석을 거부한다.
현재 테이블에서 보이는 데이터만으로 historyComplete=true를 만들어서는 안 된다.

기본 최대5,000개(허용 상한10,000개), 늦은 이벤트50개, 영향 결과200개(허용 상한1,000개), 실행120초다.
전체 사용자나 무제한 기간을 스캔하지 않는다. snapshot 내 사용자/account가 하나인지 확인한다.
발생 시각+eventID로 정렬하고, 이전/추가 이후의 20개 창 및 초기 세션 여부가 달라지는 endpoint를 찾는다.
이벤트 추가로 30분 경계가 합쳐져 초기 창 판정이 달라지는 경우도 포함한다.

- `modelVersion`: 사용한 모델·스케일러·전처리 묶음 버전. 이번 변경에서 알고리즘을 교체하지 않았다.
- `analysisVersion`: 같은 모델로 수행한 복구 분석의 버전. 기본값은 입력 이력·추가 후 입력·모델·검토 범위/근거로 결정한다.
- 새 realtime 결과도 inputEventIDs/inputDigest와 분석 종류를 기록한다. 기존 결과에 입력 이력이 없다면
  자동으로 수정했다고 주장하지 않고 거부한다. 원래 분석이 역순 도착으로 다른 입력을 썼더라도,
  그 입력 ID와 digest를 검토한 스냅샷에서 복원·확인할 수 있으면 수정 분석할 수 있다.
- 원본 결과를 덮어쓰지 않는다. 결과는 기존 principal prefix 아래 `model/reanalysis/analysisVersion/eventHash.json`에
  조건부 저장하고 supersedesKey로 기존 결과를 연결한다. 모델과 분석 버전을 혼동하지 않는다.
- 별도 `analysis-runs/principalHash/model/analysisVersion/plan.json`을 불변 저장하고, 모든 결과 저장 후에만
  complete.json을 발행한다. 중간 실패는 완료로 표시하지 않는다. 동일 입력 재실행은 기존 결과를 재사용한다.
- FastAPI는 complete.json의 소유자·버전·스냅샷·결과 키를 확인해야 재분석 결과를 적재한다.
  미완료 결과는 partial_failure로 남긴다. 장기간 실패한 run은 복구를 완료하거나 운영 검토가 필요하며,
  해당 페이지가 계속 부분 실패하면 기존 동기화 정책상 cursor가 전진하지 않을 수 있다.
- 웹 DB의 기존 raw_json에 분석 이력을 보존하므로 파괴적인 열 변경은 없다. API와 Results에서 모델/분석 버전,
  이전 결과 키를 조회할 수 있고 분석 종류 필터를 제공한다. Dashboard는 과거 재분석을 현재 그래프에서 제외한다.
  이력 목록은 수정 전·후를 함께 보여 주며 '유일 이벤트 수'나 '최종 결과만'인 목록으로 해석하면 안 된다.
- 재분석 서비스에는 알림 client가 없다. 실시간 경로의 알림도 기본 off이며, 켤 때는 운영자가
  ALERT_MAX_EVENT_AGE_SECONDS를1~86,400초 범위에서 명시해야 한다. 이 범위는 설정 검증 상한이지
  추천 운영값이 아니다. 미래 시각/허용 나이 초과 이벤트는 알림을 발행하지 않는다.
- 실시간 수신 버퍼, 자동 지연 감지·재분석 스케줄, 차량 현재 위치 갱신 서비스는 구현하지 않았다.
  재분석은 운영자가 검토한 bounded snapshot에 대한 명시적 실행 경로다. 실제 차량 제어는 없다.

### AWS 없이 재현

```bash
cd /workspace/ueba-project
uv venv --python 3.11 .venv311
uv pip sync --python .venv311/bin/python requirements.lock
PYTHONHASHSEED=0 .venv311/bin/python tools/demo_recovery.py --output .demo/recovery/my-run
```

가짜 AWS와 테스트 사용자만 사용한다. 120개 합성 입력 중1개를 늦게 넣고,
실제 Doc2Vec/OCSVM/DBSCAN으로 복구 전·후를 비교한다. 두 큐 형식과 실제 collector handler를 통과하되
Lambda 호출은 in-process adapter, Streams 전달은 직접 Detector 호출로 대체한다.
EventBridge/Lambda 관리형 재시도를 검증한 것이 아니다. 공격 탐지 정확도 평가도 아니다.
출력 디렉터리가 이미 있으면 덮어쓰지 않으므로 새 이름을 사용한다.

```bash
# 기본값은 검토용 계획만 출력하며 AWS 요청과 모델 로드가 없다.
PYTHONHASHSEED=0 .venv311/bin/python tools/reanalyze.py \
  --snapshot .demo/recovery/my-run/snapshot.json --late-events .demo/recovery/my-run/late-events.json
# 이 CLI의 --execute도 로컬 파일에만 쓴다. 기존 결과 파일은 덮어쓰지 않는다.
PYTHONHASHSEED=0 .venv311/bin/python tools/reanalyze.py \
  --snapshot .demo/recovery/my-run/snapshot.json --late-events .demo/recovery/my-run/late-events.json \
  --execute --model-root .demo/recovery/my-run/models --model-version recovery-model-v1 \
  --result-dir .demo/recovery/my-run/result-store
```

동일 명령 재실행으로 결과 재사용을 확인할 수 있다. live S3 발행은 같은 execute_reanalysis 함수를
검토된 별도 runner에서 호출할 수 있으나, 이번 CLI는 AWS client를 만들지 않는다.
S3 runner에는 baseline 읽기 및 reanalysis/analysis-runs 쓰기만 허용하고 events:PutEvents나 IAM 차단 권한을 주지 않는다.
웹 reader에는 결과 prefix뿐 아니라 자기 principal의 analysis-runs 읽기도 필요하다.
`examples/result-reader-policy.json`은 값 교체가 필요한 최소 권한 예시이며 실제 배포하지 않았다.

## 4. 시각 측정의 정확한 의미

이번 추가로 receipt에는 저장 요청 전 writeRequestedAt도 포함한다. 실제 collector handler에서는
handlerEnteredAt을 함께 기록하지만, 로컬 측정 도구가 함수를 호출하기 직전 기록하는
collectorReceivedAt과는 구분한다. DB 내부 커밋 시각은 관측하지 않는다.
`tools/latency.py`는 확보된 필드끼리만 단계별 평균/중앙값/p95/최대 및 음수 시각 차이를 계산한다.
handler/CloudWatch ingestion/read 시각이 없으면 samples=0/statistics=null이며 지연0으로 만들지 않는다.
monotonic clock의 함수 호출 시간도 별도 유지한다. 독립 receipt 파일 수를 반복 횟수로 바꾸지 않는다.

이번 로컬 현재 시각 측정도30건×3회 실제 실행했다. 결과는 validation/followup/local-latency.json에 있다.
이는 모의 DB의 처리 시간이며 이전 측정과 환경·상태가 달라 성능 개선율로 비교하지 않는다.
실제 AWS eventTime→ingestionTime→readAt→storedAt의 과거 '약5분'은 여전히 미측정/미확인이다.
현재 저장소에 확인되지 않은 CloudWatch polling 경로나 조회 주기를 새로 만들어 과거 사실처럼 쓰지 않았다.

## 검증·운영 한계

[후속 검증 기록](validation/FOLLOWUP.md)을 참고한다. 실제 AWS에서 남은 검증은 다음과 같다.

- 두 실패 큐의 실제 envelope, FunctionError·네트워크 응답 유실·visibility 및 중복 전달·개별 삭제 실패.
- IAM 최소 권한, collector 신규 GetItem/충돌 S3 권한, destination 보관·크기 제한, 실제 TTL 삭제 경쟁.
- DynamoDB TransactionConflict와 실제 S3 조건부 쓰기 동시성, 완전한 archive의 확보·검토·만료 정책.
- 실제 Lambda 컨테이너 cold start와 모델 버전 반영, 경보 나이 정책·시계 차이, 운영 알림 consumer 중복 억제.
- EventBridge/Lambda 관리형 재시도, 실제 지연 비교·차량 데이터 적용·탐지 정확도는 로컬 검증으로 대신하지 않는다.

새기능의 비용·지연을 실제 AWS에서 측정하지 않았다. 성공 응답 후 데이터가 영구 보존된다거나,
모든 경보·결과가 전역에서 정확히 한 번 처리된다고 보장하지 않는다.
