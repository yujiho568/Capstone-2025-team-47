> 아래는 첫 개선의 기록입니다. 이후 추가된 충돌 구분·복구·재분석·알림 나이 정책은 [FOLLOWUP.md](FOLLOWUP.md)가 최신 기준입니다.

# 운영 배포 준비와 검증 경계

이 문서는 **이번 개선 이후**의 절차다. AWS 자원 생성·과금·실제 차단·데이터 삭제·push는 실행하지 않았다.
`pipeline/UEBA/.terraform.lock.hcl`과 root의 Python/npm lockfile을 보관한다.
Terraform 1.10.5, provider AWS 6.71.0/archive2.8.1에서 init/validate/fmt를 검증했다.
Terraform validate는 서비스 권한/할당량이나 ASL 실행을 검증하지 않는다.

## 사전 준비

- 기존 Terraform state와 legacy 테이블/버킷의 백업을 준비한다. monitored_username은 기존 리소스의
  이름을 보존할 값이어야 한다. data source 권한과 actual account/region을 확인한다.
- 조직이 제공한 제한된 배포 역할/프로파일을 사용한다. 루트 키를 만들거나 웹 가입에 제공하지 않는다.
- 서울 리전에서 SageMaker **Processing용 ml.m5.xlarge** 지원 여부와 Processing quota,
  총 동시 job, vCPU/volume 할당량을 사전에 조회한다. 기존 main.tf의 ml.t3.medium을 지원된다고
  가정하지 않고 기본값 ml.m5.xlarge로 바꿨지만, 실제 계정에서의 가용/할당량은 미검증이다.
- v2 DynamoDB의 PITR가 활성화된 것을 확인한다. ExportTableToPointInTime에 필요하다.
- 기존 원본 CloudTrail과 export를 TTL 학습기간보다 길게 보존한다. Terraform v2 TTL은90일,
  실패 S3는365일/SQS는14일이다. 실패 큐가 만료되기 전에 보관·복구한다.

## ECR → 이미지 → Lambda

루트에서 `python tools/package_collector.py`를 먼저 실행한다.
Terraform root는 `pipeline/UEBA`다. `.build`는 source staging이며 직접 수정하지 않는다.

운영 tfvars에 `monitored_username`, `model_version`, `realtime_image_uri`, `processing_image_uri`를
지정한다. 계정/리전/ECR은 실제 값을 사용하되 비밀을 tfvars에 넣지 않는다. 처음에는 생성할 ECR
경로와 임시 digest 형식의 placeholder를 준비하고 **ECR 대상 plan만** 검토한다. placeholder로
전체 apply를 하지 않는다. bootstrap을 별도 state로 분리하려면 state 이동 계획을 먼저 세운다.

```bash
python tools/package_collector.py
cd pipeline/UEBA
terraform init
terraform validate
# 아래 명령들은 미실행 운영 절차다. plan을 검토한 뒤 사람이 승인/실행한다.
terraform plan -var-file=/secure/nonsecret.tfvars \
  -target=module.ct_pipeline.aws_ecr_repository.pipeline \
  -target=module.ct_pipeline.aws_ecr_repository.realtime -out=ecr.tfplan
terraform apply ecr.tfplan
```

두 ECR repo가 생긴 뒤 저장소 루트에서 이미지를 만든다. 플랫폼의 Docker proxy/CA 설정을 유지한다.
예시 CA mount는 공개 인증서 bundle이며 이미지에 복사하지 않는다. 일반 개발 환경에서는 secret mount
없이 시스템 신뢰를 사용할 수 있다. TLS 검증을 끄지 않는다. 현재 기반 태그는 변경될 수 있으므로
운영에서는 FROM을 검토한 digest로 고정하고 취약점 검사/빌드 provenance도 남겨야 한다.

```bash
docker build --platform linux/amd64 --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f pipeline/processing_container/Dockerfile -t <processing-ecr>:<release> .
docker build --platform linux/amd64 --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -f pipeline/realtime_container/Dockerfile -t <realtime-ecr>:<release> .
# AWS 자격증명/토큰을 파일·로그에 출력하지 않는다. 로그인은 표준 password-stdin 파이프로 수행.
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <registry>
docker push <processing-ecr>:<release>
docker push <realtime-ecr>:<release>
```

운영자는 pushed image digest를 확인해 tfvars의 두 URI를 `repo@sha256:<digest>`로 바꾼다.
새 코드에는 mutable latest 참조가 없다. 다음 전체 plan을 검토한다. legacy 테이블의 replace/destroy,
예상 외 버킷·IAM 변경이 있으면 중단한다. 기존 force_destroy/force_delete는 false로 바꿨다.
원본의 terraform destroy 후 재실행 같은 복구 절차는 사용하지 않는다.

```bash
terraform plan -var-file=/secure/nonsecret.tfvars -out=review.tfplan
terraform apply review.tfplan
```

이는 사용자가 별도 승인하여 실행하는 운영 절차이고 이번 작업에서 실행하지 않았다.

## 학습과 모델 승격

SFn는 행동 이벤트(eventID가 있는 row) 3,000건 미만이면 Done으로 학습을 건너뛴다.
marker를 행동 수로 세지 않는다. 실제 학습 입력에서도 최소3,000건을 검사한다.
오래된 테이블에는 eventID가 없으므로 원본 CloudTrail 기반 이관이 먼저 필요하다.

Export는 COMPLETED를 확인해야만 Processing으로 진행한다. 임의 S3 KeyCount로 완료를 추정하던
shortcut은 제거했다. export poll은 60회·10초, SFn 전체 TimeoutSeconds10,800,
Processing MaxRuntime7,200초다. job 생성 오류는 FailProcessing으로 끝나고 무한 quota 재시도를 하지 않는다.
SFn timeout이 외부 job을 항상 자동 종료한다고 가정하지 않는다. 실패 시 job 상태를 조회하고 운영자가
필요한 stop-processing-job을 판단한다. 이 정리 동작은 자동 실행하지 않는다.

Processing은 유일한 jobName을 MODEL_VERSION으로 써 `models/bundles/<jobName>/`에 결과를 올린다.
학습 결과가 skip/실패 또는 DBSCAN core가 없으면 새 버전으로 승격하지 않는다. model manifest는
Doc2Vec, detector/scaler, 전처리 정책, 차원, 라이브러리 버전, 체크섬을 묶는다.
S3 자동 업로드가 끝났는지, manifest·모든 파일이 일치하는지 검증한 뒤 Lambda MODEL_VERSION을
그 bundle 이름으로 바꾸어 배포한다. 모델 파일 경로를 같은 버전으로 덮어쓰지 않는다.
이전 유효 버전은 그대로 보존하므로 설정을 이전 버전으로 되돌리는 모델 롤백이 가능하다.

## 웹 계정과 source 연결

앱 SECRET_KEY(32자 이상)와 FERNET_KEY를 안전한 배포 환경으로 공급한다. 앱은 키를 Git에 넣거나
기본 키/평문으로 fallback하지 않는다. 웹 가입/로그인에는 AWS가 필요 없다. AWS 연결 API는 소유자만
STS 확인 후 등록하며 루트 credential은 거부한다. 가급적 최소 권한·단기 credential을 사용한다.
session token을 입력할 때 timezone 있는 expires_at도 제공한다. 만료 후 재등록이 필요하다.
STS 실패를 무조건 키 오타로 보지 말고 만료·권한·네트워크를 구분한다.

source binding은 신뢰된 CloudTrail actor `accountId:principalId`에 대한 운영자 설정이다.
credential 이름을 IAM 대상 이름이라고 가정하지 않는다.

```bash
PYTHONPATH=backend .venv311/bin/python tools/bind_source.py \
  --user-id <web-user-id> --credential <alias> --bucket <result-bucket> \
  --principal '<accountId>:<CloudTrail-principalId>'
# dry-run 검토/소유 확인 후에만 같은 명령에 --write 추가
```

이 도구는 AWS를 호출하지 않으며 기존 binding을 자동 변경하지 않는다. DB 접근 권한 자체가 운영자
권한이다. 앱 요청/비밀 본문을 로깅하지 않도록 reverse proxy/APM도 별도로 설정해야 한다.
FastAPI validation 응답은 rejected input을 echo하지 않는다. 브라우저→서버 요청에는 credential
등록 시 값이 필요하므로 반드시 HTTPS를 사용한다. 서버가 외부 서비스로 raw 키를 응답하지 않는다.
운영 UI 토큰은 현재 localStorage 방식으로 남아 있으므로 XSS 방어/CSP 및 httpOnly cookie 이전은
별도 보안 작업이다. 이번 변경을 전체 인증 보안 완성으로 주장하지 않는다.

## 반드시 실제 AWS에서 확인할 것

- EventBridge target permission 오류와 Lambda 내부 오류를 각각 주입해 서로 다른 큐로 가는지,
  실제 보관 body/requestPayload·retry age·실패 목적지 권한과 message size를 확인한다.
- Streams batch checkpoint, 재시도/분할, S3 전체 원본 보관, TTL REMOVE가 판정을 만들지 않는지.
- 동시 TransactWriteItems의 TransactionConflict 재시도, conditional Put의 실제 S3 동시성,
  IAM 최소 권한·교차 계정 접근 차단, throttling/timeout/목적지 장애 경보.
- PITR export COMPLETED, Processing instance/quota/job timeout, 모델 bundle 완결/승격/롤백,
  Lambda 컨테이너 cold start·메모리/아키텍처·다운로드 시간을 확인한다.
- 실제 CloudTrail 시간 정밀도/시계 오차를 기록하고 eventID 기반 지연 비교 도구를 실행한다.
  실제 경로 비교는 아직 미측정이며 합성 로컬 시간과 섞지 않는다.
- 알림 consumer의 resultKey 멱등성/outbox와 scoped-role 격리는 미구현이다.
  EMIT_ANOMALIES=false 및 remediation DISABLED 상태를 유지한다.

## 현재 환경의 외부 제한

Git 읽기(proxy 인증)는 동작하지만 `gh api`의 api.github.com은 Forbidden이었다.
GH_TOKEN의 존재만 확인했고 값을 읽거나 출력하지 않았다. 이것만으로 API 권한을 보장하지 않는다.
`public.ecr.aws` 기반 Lambda 이미지 pull도 Forbidden이었다. 환경 초안 custom allowlist에
`api.github.com`, `public.ecr.aws`를 **추가 저장**했다. 현재 실행 환경에 적용됐거나 fork 생성/이미지
빌드가 성공했다는 뜻은 아니다. 환경 설정에서 변경 검토·저장 후 환경을 publish해야 한다.
적용 후 해당 API/pull을 다시 확인하고 추가 인증/redirect host 요구는 실제 오류로 진단한다.
원본 repository push URL은 DISABLED이며 실제 fork 생성 완료 전에는 이를 fork라고 발표하지 않는다.
