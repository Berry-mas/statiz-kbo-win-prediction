# 학습, 검증, 추론, 제출 계획

## 1. 모델 전략
계획서 기준 베이스라인은 LightGBM 또는 XGBoost이며, 시간 순서 기반 검증과 soft voting 앙상블을 사용한다.

권장 운영 순서는 다음과 같다.

1. Baseline: LightGBM
2. 비교 실험: XGBoost
3. 범주형 강점 비교: CatBoost
4. 필요 시 시퀀스 모델: LSTM
5. 최종적으로 검증 점수와 운영 안정성을 함께 보고 선택

실무적으로는 처음부터 모델을 많이 벌리기보다, LightGBM 하나를 완전히 자동화하는 것이 우선이다.

---

## 2. 학습 데이터셋 구성
학습 단위는 경기 단위 1행이다.

예시 컬럼:
- 식별자: `game_id`, `game_date`
- 메타: `home_team_id`, `away_team_id`, `stadium_id`
- feature: 팀/최근/선발/불펜/라인업 관련 컬럼
- target: `target_home_win`

---

## 3. 검증 방식
계획서에 맞춰 time-based CV를 사용한다.

권장 방식:
- 시즌 초 -> 시즌 중반 예측
- 시즌 중반 -> 시즌 후반 예측
- 항상 과거 데이터만 학습, 미래 데이터는 검증

예시:
- Fold 1: 3~4월 train, 5월 valid
- Fold 2: 3~5월 train, 6월 valid
- Fold 3: 3~6월 train, 7월 valid
- Fold 4: 3~7월 train, 8월 valid

평가 지표:
- 1순위: LogLoss
- 2순위: Brier Score
- 참고: Accuracy, Calibration plot

이유:
대회 제출 값은 확률이므로, 단순 승패 정확도보다 확률 품질이 중요하다.

현재 오프라인 검증 결과:

| model | monthly CV LogLoss | monthly CV Brier | late-2025 LogLoss | late-2025 Brier |
| --- | ---: | ---: | ---: | ---: |
| `lgbm_v002` | 0.6821 | 0.2446 | 0.6873 | 0.2471 |
| `lgbm_v003` | 0.6817 | 0.2444 | 0.6813 | 0.2441 |
| `lgbm_v005` | 0.6816 | 0.2443 | 0.6823 | 0.2446 |
| `lgbm_v008` | 0.6783 | 0.2427 | 0.6753 | 0.2411 |

`lgbm_v003`는 `home_minus_away_*`, 팀 승률 비율, 결측 flag를 추가한 버전이다. late-2025 holdout에서 단순 `team_win_rate_ratio` baseline LogLoss 0.6841을 처음으로 앞섰다.
`lgbm_v005`는 같은 feature set을 사용하되 학습/검증/추론에서 일관된 고정 categorical mapping을 사용하도록 정리한 버전이다.
`lgbm_v008`은 선발 라인업 타자의 전년도 `playerSeason` 성적을 PA 가중 집계한 feature를 추가한 현재 기준 버전이다.

---

## 4. 전처리 / 학습 정책
- 수치형 결측치는 median 또는 도메인 규칙 기반 대체
- 범주형은 team_id, stadium_id, 요일, 월, 더블헤더 여부 정도만 최소 사용
- 범주형 값은 fold별 `cat.codes`가 아니라 project-level fixed mapping으로 인코딩
- 동일 의미 컬럼이 많으면 permutation importance나 SHAP으로 정리
- target leakage 의심 컬럼은 실험 전에 차단 목록 관리

---

## 5. 앙상블 전략
초기 권장:
- 동일 모델 + 다른 random seed 5개
- fold 예측 평균
- 필요 시 LightGBM + CatBoost 평균

주의:
모델 수를 늘리면 성능보다 운영 복잡도가 더 커질 수 있다.
대회 자동제출이 핵심이므로 운영 가능한 수준에서 끝내는 것이 낫다.

---

## 6. 학습 산출물
모델 학습 후 아래를 저장한다.

- 모델 파일
- feature list
- categorical feature list
- train config
- validation 결과
- feature importance
- calibration 정보
- git commit hash
- 데이터 스냅샷 버전

권장 디렉터리:
```text
artifacts/
├─ model_registry/
│  ├─ lgbm_v001/
│  │  ├─ model.pkl
│  │  ├─ feature_list.json
│  │  ├─ metrics.json
│  │  └─ train_config.yaml
```

---

## 7. 추론 파이프라인
실전 추론은 두 단계로 나뉜다.

### 7.1 사전 추론
라인업 공개 전, 선발/팀/불펜 기반 확률 산출

### 7.2 최종 추론
라인업 공개 후 라인업 피처 반영하여 최종 확률 산출

실전에서는 최종 추론값만 제출 대상으로 사용한다.

---

## 8. 제출 파이프라인
권장 서비스 분리:

### trainer
- 과거 데이터 학습
- 모델 저장
- 검증 리포트 생성

### feature_builder
- 경기별 feature 생성
- raw -> clean -> feature 변환

### inference_worker
- 당일 경기 feature 생성
- 모델 로드
- 승률 예측

### submitter
- 예측 API 전송
- 응답 저장
- 실패 시 재시도
- 제출 결과 대조

### monitor
- 제출 누락 감지
- 월간 제출률 추적
- API 차단 위험 알림

---

## 9. 배치 스케줄 예시
예시는 서버 크론 또는 Airflow, GitHub Actions self-hosted runner 등으로 구성 가능하다.

### 매일 새벽
- 전날 경기 결과 수집
- raw 적재
- clean 갱신
- team/starter/bullpen snapshot 갱신

### 매일 오전
- feature mart 갱신
- 필요 시 주간 재학습 또는 rolling retrain

### 경기 당일
- 경기 일정 조회
- 선발 확정 여부 확인
- 라인업 공개 여부 polling
- 라인업 공개 직후 최종 feature 생성
- 예측 생성
- 제출 API 전송
- 제출 결과 검증

---

## 10. 예외처리
반드시 문서화해야 하는 예외:

- 라인업 미공개 상태
- 선발 변경
- 경기 취소
- 더블헤더
- API 일시 장애
- 서버 재부팅
- 고정 IP 변경
- 50.00으로 반올림되는 예측값
- 제출 성공했지만 시스템 테이블 표시값 불일치

권장 정책:
- 50.00으로 떨어지면 소수 둘째 자리 기준 실패이므로 제출 직전 보정 규칙 적용
- 예: 50.00이면 49.99 또는 50.01로 미세 조정하는 정책을 명시적으로 둔다
- 단, 이 정책은 로그에 남겨야 하며 일관되게 적용해야 한다

---

## 11. MLOps 최소 권장안
가장 과하지 않으면서 필요한 구성만 적으면 아래 정도다.

- DB: MySQL
- object storage 또는 로컬 artifact 저장소
- 학습 실행: Python CLI
- 스케줄링: cron 또는 Airflow
- 모니터링: Slack/Webhook 알림
- 버전관리: Git + experiment log CSV 또는 MLflow
- 배포: inference 전용 Python service 또는 batch script

---

## 12. 구현 우선순위
1. raw 수집
2. feature mart
3. baseline 학습
4. 오프라인 검증
5. 단건 추론
6. 제출 API 연동
7. 자동 스케줄링
8. 모니터링/복구
9. 고도화 모델 비교
