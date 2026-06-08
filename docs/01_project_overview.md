# Statiz 승부예측 프로젝트 문서 개요

## 왜 문서를 나눠야 하는가
이 프로젝트는 단순히 모델 성능만 내는 것이 아니라, 다음을 동시에 만족해야 합니다.

- 계획서에 적은 방식과 실제 구현이 크게 어긋나지 않아야 함
- 대회 운영 규정에 맞게 API 수집/예측 제출 자동화가 되어 있어야 함
- 추후 검증 시 원천 데이터, 분석 방법, 코드 흐름을 재현할 수 있어야 함
- Codex와 Claude가 역할을 나눠 작업하더라도 파일만 보면 바로 이어서 개발할 수 있어야 함
- Codex는 

따라서 문서는 다음 4개를 기본 세트로 두는 것이 좋습니다.

1. `01_project_overview.md`
   - 프로젝트 목적, 전체 구조, 역할 분담, 문서 인덱스
2. `02_data_pipeline_and_feature_spec.md`
   - 어떤 API를 어떻게 호출하고, 어떤 테이블/피처를 만들지 정의
3. `03_training_validation_serving_plan.md`
   - 학습, 검증, 추론, 배치 실행, 제출 로직 정의
4. `04_api_contract_and_submission_rules.md`
   - 대회 운영 규정, 제출 규칙, 실패 케이스, 체크리스트 정리

## 추천 폴더 구조
```text
project-root/
├─ README.md
├─ docs/
│  ├─ 01_project_overview.md
│  ├─ 02_data_pipeline_and_feature_spec.md
│  ├─ 03_training_validation_serving_plan.md
│  └─ 04_api_contract_and_submission_rules.md
├─ configs/
│  ├─ base.yaml
│  ├─ train.yaml
│  └─ inference.yaml
├─ data_contract/
│  ├─ raw_schema.md
│  └─ feature_schema.md
├─ apps/
│  ├─ trainer/
│  ├─ inference_worker/
│  └─ submitter/
└─ notebooks/
```

## 협업 기준
- Claude: 구조 설계, 문서 정리, 리팩터링 방향, 실험 설계, 예외처리 정리
- Codex: 실제 코드 작성, 반복 수정, 파일 단위 구현, 테스트 추가
- 공통 원칙:
  - 문서 먼저 갱신 후 구현
  - 새로운 API를 붙이면 먼저 `docs/04_api_contract_and_submission_rules.md`에 반영
  - feature 추가 시 `docs/02_data_pipeline_and_feature_spec.md` 업데이트
  - 모델/검증 전략 변경 시 `docs/03_training_validation_serving_plan.md` 업데이트

## 지금 단계에서 가장 중요한 것
현재 단계에서는 아래 순서가 가장 현실적입니다.

1. API로 받을 원천 데이터 목록 확정
2. raw 저장용 MySQL 스키마 설계
3. feature mart 설계
4. 학습 파이프라인 구축
5. 추론 파이프라인 구축
6. 대회 제출 API 연동
7. 라인업 공개 직후부터 경기 15분 전까지 자동 제출 배치 완성
8. 제출 로그/재시도/모니터링 체계 완성

## 바로 실행할 체크리스트
- [ ] API 키, 인증 방식, 허용 IP 확인
- [ ] 개발/운영 서버의 고정 IP 확보
- [ ] 수집 API와 제출 API 명세 분리 정리
- [ ] raw DB 테이블 설계
- [ ] feature 생성 SQL 또는 배치 코드 설계
- [ ] baseline LightGBM 학습 코드 작성
- [ ] time-based CV 구현
- [ ] 예측 확률 보정 및 반올림 규칙 적용
- [ ] 제출 응답 저장 및 개인 페이지 대조 자동화
