# Statiz Y-wins 문서 세트

이 폴더는 스탯티즈 승부예측 프로젝트를 실제 구현 가능한 수준으로 정리한 문서 세트입니다.

## 포함 문서
- `01_project_overview.md`
- `02_data_pipeline_and_feature_spec.md`
- `03_training_validation_serving_plan.md`
- `04_api_contract_and_submission_rules.md`
- `05_data_to_model_pipeline.md`
- `06_submission_automation_mvp.md`
- `07_local_to_static_ip_server_plan.md`
- `08_lightsail_server_operations.md`
- `09_next_session_handoff.md`

## 권장 사용법
1. `04_api_contract_and_submission_rules.md`를 먼저 보고 대회 제약조건을 코드에 반영합니다.
2. `02_data_pipeline_and_feature_spec.md`를 기준으로 DB/feature 스키마를 설계합니다.
3. `03_training_validation_serving_plan.md`를 기준으로 학습/추론/제출 자동화를 구현합니다.
4. `06_submission_automation_mvp.md`를 기준으로 dry-run 자동화와 공개 대시보드 범위를 확인합니다.
5. `07_local_to_static_ip_server_plan.md`에서 고정 IP 서버 이전 기록을 확인합니다.
6. `08_lightsail_server_operations.md`를 기준으로 Lightsail systemd timer와 업데이트 스크립트를 운영합니다.
7. `09_next_session_handoff.md`에서 다음 세션의 확인 순서와 웹사이트 개선 후보를 확인합니다.
8. 구현이 바뀔 때마다 문서를 먼저 수정한 뒤 코드를 맞춥니다.

## 다음 단계
- 다음 작업은 `09_next_session_handoff.md`의 체크리스트를 기준으로 진행합니다.
