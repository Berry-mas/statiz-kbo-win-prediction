# Statiz KBO Win Prediction

Statiz 승부예측 대회를 위한 KBO 경기 홈팀 승률 예측 및 제출 자동화 프로젝트임.

현재 범위는 API raw 수집, leakage-safe feature 생성, LightGBM 앙상블 학습/검증, 당일 예측, Lightsail 고정 IP 기반 제출 자동화까지 포함함.

## 현재 상태

- 기준 모델: `artifacts/model_registry/lgbm_v008`
- 추론 대상: 정규시즌 경기의 홈팀 승리 확률
- 운영 서버: AWS Lightsail Ubuntu 24.04
- 서버 경로: `/home/ubuntu/statiz_code`
- Static IP: `3.39.52.227`
- 서버 자동화: `systemd` service/timer 기반 `auto-submit` 실행
- 실제 제출 gate: `/etc/statiz-auto-submit.env`에서 명시적으로 해제 필요
- 등록 전 기본값: dry-run only 유지
- Discord 알림: 실제 제출 성공 건이 있을 때만 발송함

## 모델

- target: `target_home_win`
  - 홈팀 승리: `1`
  - 홈팀 패배: `0`
  - 무승부/취소/노게임: 학습 제외
- prediction: `P(home team win)`
- primary metric: LogLoss
- secondary metric: Brier Score
- model: LightGBM binary classifier
- ensemble: random seed 5개 모델 평균
- categorical handling: project-level fixed mapping 사용

## 데이터

- 학습 단위: 정규시즌 경기 1행
- 학습 기간: 2023~2025 KBO 정규시즌
- feature rows:
  - 2023: 452
  - 2024: 707
  - 2025: 693
- 전체 학습 row: 1852
- model input feature count: 117 total, 6 categorical

## 검증

시간 순서 누출 방지를 위해 random split 미사용.

| 평가 | 모델 LogLoss | 모델 Brier | 비교 baseline LogLoss |
| --- | ---: | ---: | ---: |
| Monthly expanding CV | 0.6783 | 0.2427 | 0.6931 (`constant_0_5`) |
| Late-2025 holdout | 0.6753 | 0.2411 | 0.6841 (`team_win_rate_ratio`) |

평가 산출물:

- `artifacts/model_registry/lgbm_v008/metrics.json`
- `artifacts/model_registry/lgbm_v008/evaluation/model_metrics.csv`
- `artifacts/model_registry/lgbm_v008/evaluation/baseline_summary.csv`
- `artifacts/model_registry/lgbm_v008/evaluation/feature_importance.csv`

## Feature 범위

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
  - 시즌 ERA/FIP/WHIP proxy
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
- 경기 컨텍스트
  - 구장 코드
  - 요일
  - 월
  - 더블헤더 여부

## Leakage Policy

- 모든 rolling/as-of feature는 strict `< game_date` 기준 계산함
- 같은 날 경기 결과를 해당 경기 feature에 포함하지 않음
- 수집 실행일 기준 누적 지표를 과거 경기 feature에 그대로 붙이지 않음
- 학습/검증/추론 간 category mapping 불일치 방지를 위해 고정 mapping 사용함

## 제출 자동화

CLI entrypoint는 `auto-submit`임.

```bash
uv run python -m src.main auto-submit --date YYYY-MM-DD --model-version lgbm_v008
```

기본값은 dry-run임. 실제 `prediction/savePrediction` 호출은 `--execute-submit`을 명시한 경우에만 수행함.

```bash
uv run python -m src.main auto-submit \
  --date YYYY-MM-DD \
  --model-version lgbm_v008 \
  --execute-submit
```

운영 timer는 경기 시작 시간이 다른 날을 고려해 KST 12:30~18:30 사이 polling함. 각 실행은 당일 모든 경기의 `game_time`을 기준으로 T-35/T-20/T-15 정책을 경기별로 따로 판단함.

제출 정책:

- `STATIZ_MIN_LEAD_MINUTES=35`: 경기 시작 35분 전보다 이른 제출 후보 제외
- T-20 이후: 자동 제출 제외
- T-15 이후: 공식 deadline 기준 제출 금지
- 라인업 없음: 제출 가능 window 안에서는 fallback 예측 후보 처리
- 중복 제출 방지: `logs/submission_log.csv`에 같은 날짜/같은 `s_no` 성공 제출 이력이 있으면 `already_submitted` 처리
- Discord 알림: 실제 제출 성공 건만 알림

Discord 성공 알림 예시:

```text
18:30 KIA vs LG: LG 승률 57.12% (제출 홈팀 승률 57.12%)
17:00 한화 vs 삼성: 한화 승률 55.60% (제출 홈팀 승률 44.40%)
```

## 서버 운영

systemd unit:

- `ops/systemd/statiz-auto-submit.service`
- `ops/systemd/statiz-auto-submit.timer`

서버 wrapper:

- `scripts/server_auto_submit.sh`
- `scripts/server_update.sh`

서버 환경파일:

```bash
/etc/statiz-auto-submit.env
```

등록 전 안전값:

```bash
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
STATIZ_IP_REGISTERED=0
STATIZ_SKIP_COLLECT=1
STATIZ_SKIP_FEATURES=1
```

실제 제출 전 gate:

```bash
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

상세 운영 절차는 `docs/08_lightsail_server_operations.md` 기준임.

## 설치

```bash
uv sync
cp .env.example .env
```

필수 환경 변수:

```bash
API_KEY=your_api_key
API_SECRET=your_api_secret
STATIZ_REQUEST_DELAY_SECONDS=5
STATIZ_RATE_LIMIT_COOLDOWN_SECONDS=300
STATIZ_REQUEST_TIMEOUT_SECONDS=60
STATIZ_NETWORK_ERROR_COOLDOWN_SECONDS=60
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

## 주요 명령

단일 일자 raw 수집:

```bash
uv run python -m src.main collect --year 2026 --date 2026-06-11
```

연도별 raw 수집:

```bash
uv run python -m src.main collect --year 2023
uv run python -m src.main collect --year 2024
uv run python -m src.main collect --year 2025
```

teamRecord 포함 수집:

```bash
uv run python -m src.main collect --year 2025 --include-team-stats
```

clean 데이터 생성:

```bash
uv run python -m src.main clean --year 2025
```

feature 생성:

```bash
uv run python -m src.main features --year 2025
```

모델 학습:

```bash
uv run python -m src.main train --years 2023,2024,2025
```

모델 평가:

```bash
uv run python scripts/evaluate_model.py --model-version lgbm_v008 --years 2023,2024,2025
```

당일 예측:

```bash
uv run python -m src.main predict --date YYYY-MM-DD --model-version lgbm_v008
```

dry-run 제출 리허설:

```bash
uv run python -m src.main auto-submit \
  --date YYYY-MM-DD \
  --model-version lgbm_v008 \
  --skip-collect \
  --skip-features
```

deadline 정책 리허설:

```bash
uv run python -m src.main auto-submit \
  --date 2025-10-01 \
  --model-version lgbm_v008 \
  --skip-collect \
  --skip-features \
  --now 2025-10-01T17:30:00+09:00
```

품질 확인:

```bash
uv run --extra dev ruff check .
uv run --extra dev pytest
```

## Project Layout

```text
src/
├── api_client.py       # Statiz API 인증/요청
├── automation.py       # 날짜/시간 기반 제출 자동화
├── cleaner.py          # raw JSON -> clean CSV
├── collector.py        # Statiz raw API 수집
├── feature_builder.py  # leakage-safe feature 생성
├── predictor.py        # 모델 로딩 및 추론
├── submitter.py        # 제출 API 호출 및 로그
├── trainer.py          # LightGBM 학습
└── public_results.py   # 공개 결과 JSON export

ops/systemd/            # Lightsail systemd unit
scripts/                # 평가 및 서버 운영 스크립트
docs/                   # 설계/운영 문서
web/                    # 공개 결과 대시보드
```

## Git Ignore Policy

공개 repo 제외 대상:

- `.env`, `.env.*`
- `.venv/`
- `data/`
- `artifacts/`
- `logs/`
- local cache와 bytecode

공개 repo 포함 대상:

- source code
- tests
- docs
- systemd templates
- `.env.example`
