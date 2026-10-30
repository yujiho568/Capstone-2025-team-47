import React from 'react'
export default function Guide() {
  return <main style={{ padding: 24, maxWidth: 900 }}>
    <h1>개발·연결 안내</h1>
    <p>회원가입은 이메일과 비밀번호만 사용합니다. AWS 연결은 로그인 후 별도로 등록하며 루트 키를 사용하지 않습니다.</p>
    <p>결과 버킷과 사용자 전용 prefix는 서버 운영자가 연결합니다. 브라우저에서 버킷이나 객체 경로를 선택하지 않습니다.</p>
    <h2>AWS 없는 로컬 데모</h2>
    <pre>{`uv python install 3.11
uv venv --python 3.11 .venv311
uv pip sync --python .venv311/bin/python requirements.lock
PYTHONHASHSEED=0 .venv311/bin/python tools/demo.py serve
# 별도 터미널
cd frontend && npm ci && npm run dev`}</pre>
    <p>테스트 계정: demo@example.com / local-demo-only-47. 가짜 AWS와 합성 데이터로 연결을 확인합니다. 공격 탐지 정확도 평가용이 아닙니다.</p>
    <h2>배포 전 확인</h2>
    <p>빌드 기준은 pipeline/입니다. 이전 ZIP은 archive/original/에 보존하며 배포 입력으로 사용하지 않습니다.</p>
    <p>docs/IMPROVEMENTS.md와 docs/DEPLOYMENT.md를 확인하세요. ECR 생성 후 고정 이미지 빌드·업로드, 이미지 digest 지정, Terraform plan 검토 순서입니다.</p>
    <p>이 화면은 AWS 자원 생성, 과금, IAM 차단, Terraform apply를 실행하지 않습니다.</p>
  </main>
}
