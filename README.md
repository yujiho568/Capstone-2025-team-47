> **이번 작업 이후의 실행 안내 (2026-10-30):** 아래 본문은 기존 졸업과제 기록입니다.
> 새 구현·기존 구현의 차이는 [개선 기록](docs/IMPROVEMENTS.md), 실행은
> [AWS 없는 로컬 데모](docs/LOCAL_DEMO.md), 운영은 [배포 지침](docs/DEPLOYMENT.md)을 따르세요.
> 이전 ZIP은 `archive/original/`로 옮겼고 빌드 기준은 `pipeline/`입니다.
> 본문의 과거 `terraform destroy` 복구 절차와 ZIP 배포 절차는 새 구현에 사용하지 않습니다.

## 1. 프로젝트 배경

### 1.1. 국내외 시장 현황 및 문제점

클라우드 컴퓨팅은 전 세계적으로 빠르게 확산되고 있으며, 글로벌 시장조사기관 Flexera의 '2025 클라우드 현황 보고서'에 따르면 전 세계 기업의 약 94%가 클라우드 서비스를 활용 중이다. 기업의 워크로드 중 절반 이상이 퍼블릭 클라우드 환경에서 운영되고 있으며, 전체 기업 데이터의 약 60%가 퍼블릭 클라우드에 저장되고 있다.

그러나 클라우드 기술의 확산과 함께 보안 위협도 점차 정교해지고 있다:

- **계정 탈취**: 비밀번호 재사용, 단순한 패스워드 설정, 다단계 인증(MFA) 미적용 등으로 인한 계정 보안 위협
- **API 보안 결함**: 인증이 미흡하거나 보안 설계가 부족한 API를 통한 침입
- **내부자 위협**: 2023~2024년 사이 내부자에 의한 데이터 유출·분실·절도 사건이 약 28% 증가
- **경계 기반 보안의 한계**: 기존 경계 중심 보안 모델이 클라우드 환경에서 더 이상 유효하지 않음

기존 AWS 보안 서비스(GuardDuty, Security Hub, Detective)의 한계:
- 사전 정의된 탐지 규칙과 위협 인텔리전스에 의존
- 개별 이벤트 단위의 탐지로 연속적인 행동 패턴 분석 부족
- 사후 분석 중심으로 실시간 대응 기능 제한

### 1.2. 필요성과 기대효과

**필요성:**
- 제로데이 공격, 내부자 위협, 계정 탈취 등 새로운 패턴의 공격에 대한 대응 필요
- 사용자 행동 맥락(Context)을 반영한 실시간 이상 탐지 시스템 구축 필요
- AWS 환경에 특화된 경량화된 UEBA 솔루션의 부재

**기대효과:**
- 기존 보안 시스템으로 탐지하기 어려운 비정형 공격의 조기 탐지
- 계정 탈취 발생 시 초기 단계에서의 빠른 대응 가능
- 내부자 위협 및 인적 오류 기반 비의도적 사고 예방
- 실시간 이상 탐지를 통한 피해 확산 방지

## 2. 개발 목표

### 2.1. 목표 및 세부 내용

**주요 목표:**
AWS 환경에서 발생하는 보안 위협을 효과적으로 탐지하고 대응할 수 있는 사용자 및 엔터티 행동 기반 이상 탐지 시스템(UEBA) 구현

**세부 내용:**
- CloudTrail 이벤트 데이터를 활용한 사용자 행동 패턴 학습
- 초기 세션과 전체 세션을 구분한 차별화된 모델링 접근
- Doc2Vec 기반 행동 시퀀스 임베딩 및 머신러닝 기반 이상 탐지
- 실시간 이벤트 수집 및 탐지 파이프라인 구축
- Infrastructure as Code(IaC) 기반 자동화된 배포 환경 제공

### 2.2. 기존 서비스 대비 차별성

| 구분 | 기존 AWS 서비스 | 본 시스템 |
|------|----------------|-----------|
| **탐지 방식** | 룰 기반, 시그니처 기반 | 행동 패턴 기반, 머신러닝 |
| **학습 능력** | 사전 정의된 패턴만 탐지 | 조직별 특성에 맞춘 지속적 학습 |
| **분석 단위** | 개별 이벤트 중심 | 행동 시퀀스 및 맥락 분석 |
| **초기 세션 분석** | 미지원 | 로그인 직후 행동 별도 모델링 |
| **실시간 대응** | 제한적 | EventBridge 기반 실시간 탐지 |
| **배포 방식** | 수동 설정 | Terraform 기반 자동 배포 |

### 2.3. 사회적 가치 도입 계획

**공공성:**
- 오픈소스 기반 솔루션으로 중소기업도 활용 가능한 보안 기술 제공
- 클라우드 보안 분야의 연구 결과 공개를 통한 학술적 기여

**지속 가능성:**
- 서버리스 아키텍처 활용으로 에너지 효율적인 시스템 구축
- 코드 기반 인프라 관리로 반복적인 수동 작업 최소화

**환경 보호:**
- AWS의 재생에너지 기반 클라우드 인프라 활용
- 효율적인 리소스 사용을 통한 탄소 발자국 최소화

## 3. 시스템 설계

### 3.1. 시스템 구성도

![alt text](/docs/04.사진/image-3.png)

![alt text](/docs/04.사진/image.png)

![alt text](/docs/04.사진/image-5.png)


### 3.2. 사용 기술

**클라우드 인프라:**
- AWS CloudTrail: API 이벤트 수집
- AWS EventBridge: 실시간 이벤트 라우팅
- AWS Lambda: 서버리스 이상 탐지 함수
- Amazon DynamoDB: 이벤트 데이터 저장
- Amazon S3: 모델 및 결과 저장
- Amazon SageMaker: 머신러닝 모델 학습
- AWS Step Functions: 워크플로우 오케스트레이션

**머신러닝:**
- Doc2Vec: 행동 시퀀스 임베딩
- One-Class SVM: 초기 세션 이상 탐지
- DBSCAN: 전체 세션 군집화 및 이상 탐지


**웹 서비스:**
- FastAPI: 백엔드 API 서버
- React + Vite: 프론트엔드 사용자 인터페이스
- SQLite/PostgreSQL: 웹 서비스 데이터베이스
- JWT: 사용자 인증 및 권한 관리

**인프라 관리:**
- Terraform: Infrastructure as Code
- Amazon ECR: 컨테이너 이미지 저장소
- Docker: 컨테이너화된 Lambda 함수

## 4. 개발 결과

### 4.1. 전체 시스템 흐름도

```
1. 이벤트 수집 단계:
   사용자 API 호출 → CloudTrail 기록 → EventBridge 전송 → Lambda 트리거

2. 실시간 탐지 단계:
   Lambda 함수 → DynamoDB에서 최근 이벤트 조회 → 행동 시퀀스 구성 → 
   임베딩 변환 → 이상 점수 계산 → 임계값 초과 시 알림/차단

3. 모델 학습 단계:
   매일 자정 → Step Functions 트리거 → SageMaker Processing Job 실행 → 
   Doc2Vec + OCSVM/DBSCAN 학습 → 모델 S3 저장

4. 웹 서비스:
   사용자 로그인 → AWS 자격증명 등록 → S3 결과 동기화 → 대시보드 조회
```

### 4.2. 기능 설명 및 주요 기능 명세서

**1. 실시간 이상 탐지**
- 입력: CloudTrail 이벤트 스트림
- 출력: 이상 점수, 위험 등급, 탐지 결과
- 기능: 윈도우 크기 20의 행동 시퀀스를 64차원 벡터로 임베딩하여 이상 탐지

**2. 초기 세션 모델링**
- 입력: 로그인 이후 30분 이내 또는 세션 단절 후 이벤트
- 출력: One-Class SVM 기반 정상/비정상 분류
- 성능: Recall 99.14%, Precision 93.78%, Accuracy 97.32%

**3. 전체 세션 모델링**
- 입력: 모든 사용자 행동 시퀀스
- 출력: DBSCAN 군집 분석 결과
- 기능: 밀도 기반 클러스터링으로 정상 패턴과 이상 패턴 구분

**4. 자동 모델 업데이트**
- 주기: 매일 자정
- 조건: 최소 3,000건 이상의 데이터 축적 시
- 기능: Step Functions 기반 자동 파이프라인 실행

**5. 웹 대시보드**
- 기능: 이상 탐지 결과 시각화, 사용자별 위험 점수 트렌드 분석
- 지원: 초기 세션/전체 세션 구분, 필터링 및 정렬 기능

### 4.3. 디렉토리 구조 (수정 필요)

```
CAPSTONE-2025-TEAM-47/
├── README.md                # 프로젝트 개요와 실행 방법, 주요 기능 설명 문서
├── backend/                 # FastAPI 기반 백엔드 서버 관련 코드 및 DB
│   ├── app/                 # 백엔드 핵심 애플리케이션 코드 (API, 모델, 서비스 로직 등)
│   ├── requirements.txt     # 백엔드 의존성(Python 패키지) 목록
│   └── ueba_system.db       # SQLite DB 파일 (개발/테스트용 로컬 데이터 저장)
├── docs/                    # 프로젝트 문서 자료 모음
│   ├── 01.보고서/           # 최종/중간/착수 보고서 문서 파일
│   ├── 02.포스터/           # 발표용 포스터 PPT
│   ├── 03.발표자료/         # 발표용 PPT 프레젠테이션 자료
│   └── 04.사진/             # 시연 캡처, 프로젝트 관련 사진
└── frontend/                # React + Vite 기반 프론트엔드 코드
    ├── eslint.config.js     # ESLint 설정 파일 (코드 품질 검사 규칙)
    ├── index.html           # SPA 엔트리 포인트 HTML
    ├── package-lock.json    # 설치된 프론트엔드 패키지의 고정 버전 관리
    ├── package.json         # 프론트엔드 프로젝트 메타데이터 및 의존성 목록
    ├──src/                 # 프론트엔드 소스 코드 (React 컴포넌트, 페이지, 스타일 등)
    ├──vite.config.js       # Vite 빌드/개발 서버 설정 파일
    └── public/              # 정적 파일 저장소
         ├── UEBA.zip                 # 전체 UEBA 프로젝트 관련 리소스/코드 압축본
         ├── processing_container.zip  # 데이터 처리(배치/분석) 컨테이너 관련 코드/설정 압축본
         ├── realtime_container.zip    # 실시간 처리 컨테이너 관련 코드/설정 압축본
         ├── step1.png                
         ├── step4.png                
         ├── step4-1.png              
         ├── step4-2.png              
         ├── step5.png                
         └── vite.svg                  # Vite 로고 (프론트엔드 빌드 도구 관련 정적 이미지)
```

### 4.4. 산업체 멘토링 의견 및 반영 사항

**멘토 피드백 1**: 대규모 로그 처리와 실시간 분석 성능 검증 필요
- **반영 사항**: 아키텍처를 이벤트 수집/탐지 영역과 모델링 영역으로 분리하여 시스템 안정성 확보. IAM 계정 단위로 독립 구성하여 분산 처리 가능한 구조로 설계

**멘토 피드백 2**: 이상 탐지 성능과 사용자 행동 프로파일링 정확도의 정량적 결과 부족
- **반영 사항**: 실제 데이터셋을 활용한 성능 평가 결과 추가:
  - OCSVM 초기 세션 모델: F1-score 96.39%
  - DBSCAN 전체 세션 모델: 의미 있는 군집 형성 확인
  - Doc2Vec 임베딩의 정상/공격 데이터 분리 능력을 PCA로 시각화

## 5. 설치 및 실행 방법

### 5.1. 설치절차 및 실행 방법

**준비 사항:**
- AWS 계정 및 적절한 IAM 권한
- Python 3.12+ 
- Node.js 18+
- Terraform 1.0+

**자동 설치 (권장):**
```bash
# 프로젝트 다운로드
git clone https://github.com/your-repo/ueba-system.git
cd ueba-system
```

**AWS 인프라 배포:**
```bash
# Terraform 초기화 및 배포
cd terraform
terraform init
terraform plan
terraform apply
```

**백엔드 실행:**
```bash
# 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 서버 시작
uvicorn app.main:app --reload --port 8000
```

**프론트엔드 실행:**
```bash
cd frontend
npm install
npm run dev
```

**접속 정보:**
- 백엔드 API: http://localhost:8000
- 프론트엔드: http://localhost:5173

### 5.2. 오류 발생 시 해결 방법

**1. Terraform 배포 실패:**
```bash
# IAM 권한 확인
aws sts get-caller-identity

# 리소스 정리 후 재배포
terraform destroy
terraform apply
```

**2. Lambda 함수 오류:**
```bash
# CloudWatch Logs 확인
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/ueba"

# ECR 이미지 빌드 및 푸시
docker build -t ueba-lambda .
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com
```

**3. 웹 서비스 연결 오류:**
```bash
# CORS 설정 확인
# .env 파일의 CORS_ORIGINS 설정

# 데이터베이스 연결 확인
python -c "from app.database import engine; print(engine.url)"
```

## 6. 소개 자료 및 시연 영상

### 6.1. 프로젝트 소개 자료
- [프로젝트 발표 자료](/docs/03.발표자료/발표자료.pptx)

### 6.2. 시연 영상(수정 필요)
- [발표 영상 주소](https://youtube.com/demo-video)

주요 시연 내용:
- Terraform을 통한 원클릭 AWS 인프라 배포
- 실시간 CloudTrail 이벤트 수집 및 이상 탐지
- 웹 대시보드를 통한 결과 시각화
- 계정 탈취 시나리오에서의 조기 탐지 성능

## 7. 팀 구성

### 7.1. 팀원별 소개 및 역할 분담

**최두환** (202055611)
- 역할: 팀장, 머신러닝 모델 개발
- 담당: Doc2Vec 임베딩, OCSVM/DBSCAN 모델 구현, 성능 평가
- 기술 스택: Python, scikit-learn, gensim, AWS SageMaker

**심여준** (202045819)
- 역할: 클라우드 아키텍처 설계
- 담당: AWS 서비스 연동, Lambda 함수 개발, 실시간 파이프라인 구축
- 기술 스택: AWS (CloudTrail, EventBridge, Lambda, DynamoDB), Terraform

**유지호** (202055568)
- 역할: 웹 서비스 개발
- 담당: FastAPI 백엔드, React 프론트엔드, 사용자 인터페이스 설계
- 기술 스택: FastAPI, React, SQLAlchemy, JWT

### 7.2. 팀원별 참여 후기

**최두환**: 
"UEBA라는 새로운 분야에 도전하며 머신러닝 모델의 실제 적용 과정을 경험할 수 있었습니다. 특히 초기 세션과 전체 세션을 구분한 차별화된 접근 방식을 개발하면서, 도메인 지식의 중요성을 깊이 이해하게 되었습니다. 실제 성능 평가에서 F1-score 96%를 달성한 것은 큰 성취감을 주었습니다."

**심여준**: 
"서버리스 아키텍처와 IaC를 활용한 클라우드 네이티브 시스템 구축 경험이 매우 흥미로웠습니다. EventBridge와 CloudTrail의 지연시간 이슈를 해결하는 과정에서 AWS 서비스 간의 특성을 깊이 이해할 수 있었고, Terraform을 통한 인프라 자동화의 중요성을 체감했습니다."

**유지호**: 
"보안 도메인의 복잡한 데이터를 사용자 친화적인 웹 인터페이스로 구현하는 과정이 도전적이었습니다. 특히 실시간 이상 탐지 결과를 시각화하고, AWS 자격증명 관리 기능을 안전하게 구현하면서 보안과 사용성 사이의 균형을 맞추는 법을 배웠습니다."

## 8. 참고 문헌 및 출처

[1] 신윤호 기자 (2024.06.18), "올해 전 세계 퍼블릭 클라우드 지출 20% 증가", 전자신문
- https://elec4.co.kr/m/article/articleView.asp?idx=32584

[2] Singh, A., & Vimal, S. (2024). UEBA: An In-depth Exploration of User and Entity Behavior Analytics. Technology Update, Informatics.
- https://informatics.nic.in/files/websites/april-2024/ueba.php

[3] Dai, A. M., Olah, C., & Le, Q. V. (2015). Document Embedding with Paragraph Vectors. arXiv.
- https://arxiv.org/abs/1507.07998

[4] Insider Threat Statistics: (2025's Most Shocking Trends). StationX.
- https://www.stationx.net/insider-threat-statistics/

[5] Martín, A. G., et al. (2021). An approach to detect user behaviour anomalies within identity federations. Computers & Security, 108, 102356.

[6] Expel. (2023). A Defender's Cheat Sheet -- MITRE ATT&CK in AWS.
- https://expel.com/wp-content/uploads/2023/01/Expel-AWS-defenders-cheat-sheet-111020.pdf

[7] Red Canary. By the same token: How adversaries infiltrate AWS cloud accounts.
- https://redcanary.com/blog/threat-detection/aws-sts/

[8] MITRE. MITRE ATT&CK Technique T1526: Cloud Service Discovery.
- https://attack.mitre.org/techniques/T1526/

[9] AWS Documentation. Amazon CloudTrail User Guide.
- https://docs.aws.amazon.com/cloudtrail/

[10] HashiCorp. Terraform Documentation.
- https://developer.hashicorp.com/terraform
