# 실제 로컬 검증 기록

검증일: 2026-10-30 (한국 시간). 아래 건수는 실행 로그에서 옮겼으며 목표값/과거 성능값이 아니다.
실제 AWS 통합 테스트, 실제 GitHub fork 생성, AWS 지연 비교는 미완료다.

| 실제 실행 | 결과 | 범위 |
|---|---|---|
| Python 3.11.17 + 고정 의존성 import, uv pip check | 통과, 설치 패키지70개 충돌 없음 | FastAPI0.104.1/Pydantic2.7.4/pydantic-settings2.2.1/gensim4.3.2 포함 |
| `python -m pytest -q` | **27 passed**, 10 deprecation warnings, 13.12초 | Moto·실제 로컬 DB·실제 모델·예외 주입·오프라인 ASL 참조 검사 |
| frontend `npm run lint` | 통과, 오류/경고0 | 정적 검사 |
| frontend `npm run build` | 통과, 모듈56개 | Vite production bundle; 브라우저 자동화 아님 |
| Terraform init/validate/fmt -check | 통과 | AWS6.71.0/archive2.8.1, 실제 plan/apply 아님 |
| 스테이징 collector의 격리 import (`python -I`) | 통과 | 생성 ZIP 입력 디렉터리의 package 경로를 실제 사용 |
| `tools/demo.py run` 및 serve seed | 입력120, 저장120, 중복 재입력은duplicate | Moto 수집 |
| 로컬 실제 ML | 학습창82, 결과82, 입력 부족38 | 60개씩 두 세션, 첫19개씩 판정 보류 |
| 첫 API 동기화·조회 | imported82/errors0, queried82 | 인증·암호화·SQLite 경유; [JSON 증거](local-demo.json) |
| 데모 재실행 | imported0/skipped82/errors0, queried82 | 로컬 모델 재사용과 웹 DB 중복 처리; Moto 자원은 새로 생성 |
| 실제 localhost HTTP | health ok, 로그인 후 결과82개, 무인증401 | uvicorn server 실제 시작/종료 확인 |
| Processing Docker 이미지 build | 통과 | TLS 검증 유지, proxy CA는 build secret |
| Processing 컨테이너 비루트 실행, network none | 학습120건/82창 성공 | actual main.py + DynamoDB export loader + 실제 모델, 64차원 기본 |
| 같은 이미지의 운영 최소건수 확인 | status skipped/count120/minimum3000 | `MIN_TRAIN_EVENTS` override 없이 확인 |
| Realtime Docker 이미지 build | **차단** | public.ecr.aws manifest HEAD Forbidden. 코드는 로컬 import/테스트했지만 Lambda base 미검증 |
| 사용자 Git 저장소 fetch | 성공 | origin/main `46866d26a2866d1c8fa23e0a2d00ac7637b7f814`; 기존 main 변경/강제 push 없음 |
| GitHub API fork 정보 조회 | **차단** | api.github.com Forbidden. origin 설정만으로 실제 fork라고 주장하지 않음 |

27개 테스트는 다음을 포함한다:

- 정상/동시 중복/응답 유실 후 재처리/같은 시각 별도 이벤트/eventID 동일·identity 변경 재입력.
- 저장 실패 및 비중복 transaction 취소의 예외 전파, 원본 invalid JSON·필수 필드 누락 S3 보관.
- TTL 숫자 및 실제 완료 receipt와 요청 시각 구별, REMOVE/MODIFY/marker 제외, 배치 중간 실패 checkpoint.
- 30분 경계, 사용자별 분리, 동일 시각 정렬, 20개 미만, 긴 세션 최대41개 조회.
- 실제 Doc2Vec/OCSVM/DBSCAN, 모델 누락·manifest 불일치·버전 전환/cache, 결과 키 충돌 방지.
- 결과 저장 후 알림 실패/재시도(알림은 Mock), S3 반복·동시 첫 삽입, 페이지·부분 실패·불변 객체 변경.
- schema·위험 범위, 저장소 연결 장애, FK IntegrityError를 중복으로 숨기지 않음, AWS 오류 종류 분류.
- 무인증 및 다른 사용자 import/조회/credential/격리 접근 거부, 암호화 키 부재·legacy plaintext 거부,
  임시 token/만료 저장·만료 거부, 루트 키 거부, validation 응답의 비밀 input 비노출.
- ASL state 참조/유한 작업 종료, 버전별 summary 적재/반복/내용 변경 실패, replay·latency 계산.

초기 실패에서 수정한 환경/코드 문제:

- Python3.12에서 gensim4.3.2 wheel 대신 빌드를 시도하다 clang 부재로 실패 → 운영과 맞는3.11 wheel 사용.
- 관리 환경의 기본 AWS guard profile 때문에 Moto 내부 metadata session 생성 실패 → mock 컨텍스트 안에서만
  가짜 프로파일을 명시적으로 선택. 실제 런타임의 인증 변수/가드·proxy는 변경하지 않음.
- 제한 sandbox에서 TestClient 이벤트 루프가 대기 → 로컬 IPC를 허용한 실행에서 실제 테스트 완료.
- 컨테이너 COPY가 체크아웃의0600/0700을 보존해 비루트 source 읽기 실패 → 이미지 내부 read/traverse 권한 수정 후 성공.
- 기존 frontend의 require/미정의 변수·미사용 변수/refresh 경계 및 hook 의존성 오류 정리 후 lint/build 성공.

남은 경고는 passlib/crypt, Starlette/python-multipart, httpx TestClient app shortcut, legacy Pydantic Config의
deprecated API다. 테스트 실패로 숨기지 않았으며 버전별 업그레이드 작업이 남아 있다.
AWS Lambda 관리형 재시도, EventBridge 전달, IAM 강제, TTL 실제 삭제, Streams 체크포인트,
S3 조건부 쓰기의 서비스 동시성, 계정 quota, 실제 탐지 정확도를 검증한 결과로 확대 해석하지 않는다.
