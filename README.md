# Statiz KBO Win Prediction

Statiz 승부예측 대회를 위한 KBO 경기 홈팀 승률 예측 프로젝트입니다.

현재 1차 목표는 **제출 자동화가 아니라**, API raw 수집부터 누출 없는 학습/검증 데이터셋 생성, LightGBM baseline 학습과 검증 점수 확인까지입니다.

## 1차 Baseline Scope

### 포함

- Statiz API raw JSON 수집
- 2023~2025 정규시즌 경기 단위 train/validation feature 생성
- 경기 시작 전에 알 수 있는 정보만 사용하는 leakage-safe feature mart 생성
- 선발 라인업의 전년도 타자 성적 기반 feature 생성
- 월별 expanding CV
- 2025 시즌 후반 holdout 검증
- LightGBM baseline 학습 및 LogLoss/Brier Score 확인

### 제외

- 예측 결과 제출 자동화
- 경기 당일 라인업 공개 후 최종 제출 배치
- 타자 `playerDay` 기반 최근 타격감 feature
- 구장별 split, 좌우 상성 같은 2차 고도화 피처
- 운영 모니터링/알림

## 현재 머신러닝 방법론

현재 모델은 **홈팀 승리 확률**을 예측합니다.

- target: `target_home_win`
  - 홈팀 승리: `1`
  - 홈팀 패배: `0`
  - 무승부/취소/노게임: 학습 제외
- prediction: `P(home team win)`
- primary metric: LogLoss
- secondary metric: Brier Score

### 학습 데이터 구성

- 단위: 정규시즌 경기 1행
- 기간: 2023~2025 KBO 정규시즌
- 현재 feature rows:
  - 2023: 452
  - 2024: 707
  - 2025: 693
- 전체 학습 row: 1852
- 현재 model input feature count: 117 total, 6 categorical

### 검증 전략

시간 순서 누출을 피하기 위해 random split은 사용하지 않습니다.

- Monthly expanding CV
  - 과거 경기만 학습하고 다음 월을 검증합니다.
  - validation row가 너무 적거나 한 클래스만 있는 fold는 제외합니다.
- Late-2025 holdout
  - `2025-09-01` 이후 97경기를 별도 holdout으로 평가합니다.

### 모델

- LightGBM binary classifier
- 동일 설정 + 다른 random seed 5개 앙상블
- 최종 예측은 seed model 5개의 평균 확률
- 범주형 피처는 고정 project-level mapping으로 compact integer code화합니다.
  - 팀/구장/API 원본 코드를 fold마다 `cat.codes`로 다시 매핑하지 않습니다.
  - 학습/검증/추론의 category mapping 불일치를 방지합니다.

### Baseline 비교

모델 평가는 아래 단순 baseline과 함께 비교합니다.

- `constant_0_5`: 모든 경기 홈팀 승률 50%
- `train_home_win_prior`: 학습 구간의 홈팀 승률 평균
- `team_win_rate_ratio`: `home_win_rate / (home_win_rate + away_win_rate)`

현재 기준 모델은 `artifacts/model_registry/lgbm_v008`입니다.

| 평가 | 모델 LogLoss | 모델 Brier | 비교 baseline LogLoss |
| --- | ---: | ---: | ---: |
| Monthly expanding CV | 0.6783 | 0.2427 | 0.6931 (`constant_0_5`) |
| Late-2025 holdout | 0.6753 | 0.2411 | 0.6841 (`team_win_rate_ratio`) |

평가 산출물:

- `artifacts/model_registry/lgbm_v008/metrics.json`
- `artifacts/model_registry/lgbm_v008/evaluation/model_metrics.csv`
- `artifacts/model_registry/lgbm_v008/evaluation/baseline_summary.csv`
- `artifacts/model_registry/lgbm_v008/evaluation/feature_importance.csv`

## Data Strategy

1차 baseline은 가능한 전량 수집이 아니라 **최소 수집으로 빠르게 검증 가능한 모델을 만드는 방식**으로 진행합니다.

### 1차 raw 수집 범위

- `gameSchedule`: 경기 일정과 결과
- `gameBoxscore`: 경기별 박스스코어
- `gameLineup`: 선발 라인업과 선발투수 식별
- `teamRecord`: 참고용 팀 기록
- `playerDay`: 선발투수 경기별 기록
- `playerSeason`: 선발투수 및 선발 라인업 타자 시즌 기록

### 2차 확장 후보

1차 baseline의 결측률, feature importance, validation score를 보고 필요할 때 확장합니다.

- 선발 라인업 타자 `playerDay`
- `playerSituation` 기반 구장별 split
- 홈/원정 split
- 좌우 상성
- 라인업 최근 타격감
- 전 시즌 가중 이동평균

## Leakage Policy

학습 feature는 항상 **대상 경기 이전에 알 수 있었던 정보만** 사용합니다.

중요한 결정:

- 기존 `team_daily_snapshot` 방식처럼 수집 실행일 기준 시즌 누적 지표를 과거 경기에 그대로 붙이지 않습니다.
- 팀 전력 피처는 우선 `games.csv`와 `boxscore` raw에서 경기 전까지의 누적/rolling 지표로 재구성합니다.
- OPS, wOBA, wRC+, FIP 같은 고급 Statiz 지표는 API가 날짜 기준 as-of 조회를 지원하는지 확인한 뒤 2차로 붙입니다.
- rolling feature는 strict `< game_date` 기준으로 계산합니다.
- 같은 날 경기 결과가 해당 경기 feature에 들어가면 안 됩니다.

## 1차 Feature Set

필수 feature는 다음 범위로 제한합니다.

- 팀 시즌 전력 proxy
  - 경기 전 승률
  - 경기 전 평균 득점/실점
  - 경기 전 득실점 차
  - 홈/원정 팀의 시즌 누적 경기 수
- 최근 흐름
  - 최근 5경기 승률
  - 최근 5경기 평균 득점/실점
  - 최근 5경기 득실점 차
- 선발투수
  - 시즌 ERA/FIP/WHIP 또는 raw에서 계산 가능한 proxy
  - 최근 3경기 성과
  - 직전 등판 투구수
  - 휴식일
- 불펜
  - 최근 3일 불펜 이닝
  - 최근 3일 불펜 실점/ERA proxy
- 선발 라인업 타자
  - 전년도 PA 합계
  - 전년도 OPS/wOBA/wRC+의 PA 가중 평균
  - 전년도 WAR/HR/SB 합계
  - 상위 4번 타순 전년도 OPS/wRC+의 PA 가중 평균
  - 전년도 성적 커버리지와 좌/스위치 타자 구성
- 홈/원정 상대 비교
  - 홈팀 피처 - 원정팀 피처 차이값
  - 팀 승률 비율 `home_win_rate / (home_win_rate + away_win_rate)`
  - 최근 승률 비율
  - 선발/불펜 정보 결측 flag
- 경기 컨텍스트
  - 구장 코드
  - 요일
  - 월
  - 더블헤더 여부

## Validation Plan

검증은 두 가지를 함께 사용합니다.

### 1. Monthly Expanding CV

각 시즌 내에서 과거 월로 학습하고 다음 월을 검증합니다.

예시:

- 3~4월 train -> 5월 validation
- 3~5월 train -> 6월 validation
- 3~6월 train -> 7월 validation
- 3~7월 train -> 8월 validation
- 3~8월 train -> 9월 validation

### 2. 2025 Late-season Holdout

2023~2025 대부분을 학습에 사용하고, 2025 시즌 후반 구간을 별도 holdout으로 남겨 미래 예측에 가까운 성능을 확인합니다.

주요 지표:

- Primary: LogLoss
- Secondary: Brier Score
- 참고: Accuracy, calibration

## Current Data State

raw JSON은 재사용 가능한 원천 데이터입니다. clean/features/model artifacts는 재생성 가능한 산출물로 취급합니다.

현재 확인된 raw 상태:

- 2025: schedule, boxscore, lineup, roster, team_stats, 선발투수 `playerDay/playerSeason`, 선발 라인업 타자 `playerSeason`
- 2023~2024: 선발 라인업 타자 `playerSeason`
- 2026: 일부 `playerSeason`

기존 clean CSV는 수집 실행일 기준 집계가 섞여 있어 1차 baseline 기준으로 폐기하고 다시 생성합니다.

## Commands

환경 설정:

```bash
uv sync
cp .env.example .env
```

환경 변수:

```bash
API_KEY=your_api_key
API_SECRET=your_api_secret
STATIZ_REQUEST_DELAY_SECONDS=5
STATIZ_RATE_LIMIT_COOLDOWN_SECONDS=300
STATIZ_REQUEST_TIMEOUT_SECONDS=60
STATIZ_NETWORK_ERROR_COOLDOWN_SECONDS=60
```

API 차단을 피하기 위해 기본 요청 간격은 5초, 429 응답 후 기본 쿨다운은 300초로 둡니다. 오래 걸려도 안전하게 수집하는 쪽을 우선합니다.

Discord 알림을 사용하려면 `.env`에 웹훅 URL을 넣습니다.

```bash
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

연도별 raw 수집:

```bash
uv run python -m src.main collect --year 2023
uv run python -m src.main collect --year 2024
uv run python -m src.main collect --year 2025
```

`teamRecord` 원본까지 같이 받고 싶을 때만 아래처럼 옵션을 붙입니다.

```bash
uv run python -m src.main collect --year 2025 --include-team-stats
```

clean 데이터 생성:

```bash
uv run python -m src.main clean --year 2023
uv run python -m src.main clean --year 2024
uv run python -m src.main clean --year 2025
```

feature 생성:

```bash
uv run python -m src.main features --year 2023
uv run python -m src.main features --year 2024
uv run python -m src.main features --year 2025
```

baseline 학습:

```bash
uv run python -m src.main train --years 2023,2024,2025
```

baseline 비교 및 feature importance 생성:

```bash
uv run python scripts/evaluate_model.py --model-version lgbm_v008 --years 2023,2024,2025
```

제출 자동화 dry-run MVP:

```bash
uv run python -m src.main auto-submit --date 2026-06-09 --model-version lgbm_v008
```

기본값은 dry-run입니다. 이 명령은 수집, 정제, feature 생성, 예측, 제출 예정 payload 기록,
Discord 알림, 공개 대시보드용 JSON 생성을 실행하지만 실제 `prediction/savePrediction` 제출은 하지 않습니다.
실제 제출은 운영 검증 후 아래처럼 명시적으로 켭니다.

```bash
uv run python -m src.main auto-submit --date 2026-06-09 --model-version lgbm_v008 --execute-submit
```

로컬 데이터를 재사용해서 API 수집 없이 흐름만 확인할 때:

```bash
uv run python -m src.main auto-submit --date 2026-06-09 --model-version lgbm_v008 --skip-collect --skip-features
```

과거 경기일로 deadline 정책을 리허설할 때는 `--now`로 스케줄러 기준 시각을 주입합니다.

```bash
uv run python -m src.main auto-submit --date 2025-10-01 --model-version lgbm_v008 --skip-collect --skip-features --now 2025-10-01T17:30:00+09:00
```

현재 기준 모델:

- `artifacts/model_registry/lgbm_v008`
- feature rows: 2023 452, 2024 707, 2025 693
- model input feature count: 117 total, 6 categorical
- monthly expanding CV: LogLoss `0.6783`, Brier `0.2427`
- late-2025 holdout: LogLoss `0.6753`, Brier `0.2411`
- late-2025 holdout 기준 단순 `team_win_rate_ratio` baseline LogLoss `0.6841`보다 개선됨

품질 확인:

```bash
poe lint
poe test
poe all
```

## Project Layout

```text
src/
├── api_client.py
├── automation.py
├── collector.py
├── cleaner.py
├── feature_builder.py
├── notifications.py
├── trainer.py
├── predictor.py
├── public_results.py
├── submitter.py
└── main.py

data/
├── raw/       # API 원천 JSON, 보존 대상
├── clean/     # 재생성 가능한 정제 CSV
└── features/  # 재생성 가능한 feature CSV

artifacts/
└── model_registry/  # 재생성 가능한 모델 산출물
```

## Development Notes

- 패키지 관리는 `uv`를 사용합니다.
- 직접 `pip`를 사용하지 않습니다.
- 포맷/린트는 `ruff`, 테스트는 `pytest`를 사용합니다.
- public 함수와 클래스에는 타입힌트와 docstring을 유지합니다.
- feature나 검증 전략이 바뀌면 `docs/02_data_pipeline_and_feature_spec.md` 또는 `docs/03_training_validation_serving_plan.md`도 함께 갱신합니다.
