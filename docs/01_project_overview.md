# Statiz Y-wins 프로젝트 개요

## 목표

Statiz KBO 승부예측 대회용 수집, feature 생성, 학습, 예측 제출, 공개
대시보드를 하나의 재현 가능한 파이프라인으로 운영함.

## 현재 구성

```text
project-root/
├─ src/                  # 수집, 정제, feature, 학습, 예측, 제출, 공개 JSON 생성
├─ tests/                # API, 자동화, feature, 예측, 알림, 공개 결과 테스트
├─ scripts/              # 서버 실행, 수동/자동 제출, 공개 결과 publish 스크립트
├─ ops/systemd/          # 자동 제출 systemd service/timer
├─ docs/                 # 데이터, 모델, 제출, 운영 문서
└─ web/                  # Vercel 공개 대시보드
```

로컬/서버에서 생성되는 `data/`, `logs/`, `artifacts/`, `.env`는 Git에 올리지
않음.

## 주요 흐름

1. `collector.py`가 Statiz API raw 데이터를 저장함.
2. `cleaner.py`가 raw JSON을 clean CSV로 변환함.
3. `feature_builder.py`가 경기 전 feature matrix를 생성함.
4. `trainer.py`가 LightGBM 모델 artifact를 생성함.
5. `predictor.py`가 모델을 로드해 홈팀 승률을 예측함.
6. `automation.py`가 제출 가능 여부를 판단하고 `submitter.py`를 호출함.
7. `public_results.py`가 공개 가능한 요약만 `web/public/results.json`으로 내보냄.
8. `web/` 대시보드가 sanitized JSON과 팀 로고를 표시함.

## 운영 원칙

- 제출 API 호출은 등록 IP 서버 환경에서만 수행함.
- 공개 웹에는 finalized 결과, 제출 요약, 모델 운영 지표처럼 사용자에게 보여도 되는
  값만 노출함.
- raw API 응답, feature matrix, credential, 서버 주소, private path, gate 실제 값은
  공개 JSON과 문서에 넣지 않음.
- 수동 제출과 자동 제출은 같은 모델 버전을 기준으로 동작하되, 제출 로그의 `source`
  값으로 서로의 중복 제출 판단을 분리함.

## 문서 사용법

- API/제출 제약: `04_api_contract_and_submission_rules.md`
- 데이터와 feature: `02_data_pipeline_and_feature_spec.md`,
  `05_data_to_model_pipeline.md`
- 학습/검증/서빙: `03_training_validation_serving_plan.md`
- 자동화와 운영: `06_submission_automation_mvp.md`,
  `08_lightsail_server_operations.md`
