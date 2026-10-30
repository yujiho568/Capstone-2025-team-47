# 발생부터 저장 응답까지의 로컬 실측 (2026-10-30)

이번 측정은 Moto의 메모리 DynamoDB에 대한 측정이다. AWS CloudTrail/EventBridge/CloudWatch Logs의
전달 지연, 주기적 로그 읽기, 실제 AWS DynamoDB의 지연은 포함하지 않는다. 과거의 '약5분'을
검증하거나 어느 AWS 구간이 원인인지 판정한 결과가 아니다.

실행:

```bash
PYTHONHASHSEED=0 .venv311/bin/python tools/measure_local_latency.py \
  --count 30 --repetitions 3 --output .demo/latency/new-measurement
PYTHONHASHSEED=0 .venv311/bin/python -m pytest -q tests/test_tools.py
```

측정 도구는 고정된 과거 시각을 사용하지 않고 이벤트를 생성할 때 현재 UTC 시각을 기록한다.
각 회차별 resource 준비와 warmup1건은 제외했고, 순차 이벤트30건씩 실제3회, 총90건을 실행했다.
고의 지연은 넣지 않았다. eventID로 대응하여 완료90건, 누락0건, 중복 저장0건을 확인했다.
이 범위의 숫자는 실제 AWS에서의 누락/중복이나 안정성 보장을 뜻하지 않는다.

| 회차 | 대응 건수 | 평균(초) | 중앙값(초) | p95(초) | 최대(초) |
|---|---:|---:|---:|---:|---:|
|1|30|0.007518|0.004513|0.011203|0.067044|
|2|30|0.015116|0.012151|0.016048|0.091221|
|3|30|0.023427|0.017950|0.051654|0.114153|

회차1의 첫 이벤트(한국 시간, UTC+09:00):

- 이벤트 생성 시각: 21:32:05.483226
- 수집 코드 진입 직전: 21:32:05.483230
- DB 저장 요청 직전: 21:32:05.483244
- 트랜잭션 저장 성공 응답 후: 21:32:05.485664

`timestamp`는 원래 이벤트 발생 시각이며 저장 완료 시각으로 해석하지 않았다.
`writeRequestedAt`은 DB 요청 전, receipt의 `storedAt`은 성공 응답 직후다.
실제 DB 내부 커밋 순간을 서버에서 직접 관측했다는 뜻은 아니다.
단일 호스트의 합성 시각과 모의 저장이므로 AWS 초 단위 CloudTrail eventTime의 정밀도와 다르다.
원본 측정 JSONL과 전체 보고서는 [latency/](latency/)에 보존했다.

현재 확인한 일반 소스와 세 ZIP의 내부 Python/Terraform/JS에서 filter_log_events,
get_log_events, start_query, lookup_events 호출을 찾지 못했다. 수집 코드와 IaC는
CloudTrail→EventBridge→수집 Lambda→DynamoDB 경로다. 이는 과거 다른 배포 버전에도
주기적 CloudWatch 조회가 없었다는 증거는 아니다.

실제 AWS 측정을 실행하지 못한 이유: 관리 환경에 준비된 AWS identity/credential binding이
없고 실제 측정 대상 log group/table 설정도 제공되어 있지 않다. 비밀값을 읽거나 요청하지 않았다.
과거 '약5분'을 확인하려면 같은 eventID에 대해 CloudTrail eventTime, 해당 로그의 CloudWatch
관측 시각, 수집 코드의 관측 시각, DB 저장 성공 receipt를 확보해 비교해야 한다.
CloudWatch ingestionTime은 로그 수집 서비스가 기록을 수락한 시각이며 코드가 읽은 시각과 다르다.
기존 테이블의 timestamp만으로는 DB 저장 완료 시각을 소급해서 알아낼 수 없다.
