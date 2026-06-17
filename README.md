# Y-wins KBO Forecast

Statiz 승부예측 대회를 위한 KBO 경기 홈팀 승률 예측 및 제출 자동화 프로젝트임.

현재 범위는 API raw 수집, leakage-safe feature 생성, LightGBM 앙상블 학습/검증, 당일 예측, 고정 IP 서버 기반 제출 자동화, Vercel 공개 대시보드까지 포함함.

## 현재 상태

- 기준 모델: `artifacts/model_registry/lgbm_v008`
- 추론 대상: 정규시즌 경기의 홈팀 승리 확률
- 운영 서버: 고정 IP Linux 서버
- 서버 자동화: `systemd` service/timer 기반 `auto-submit` 및 공개 결과 publish 실행
- 공개 대시보드: https://y-wins-kbo-forecast.vercel.app
- 모델 해석 페이지: https://y-wins-kbo-forecast.vercel.app/feature-analysis
- 모델/변수 설명 페이지: https://y-wins-kbo-forecast.vercel.app/model-guide
- Vercel root directory: `web`
- 실제 제출 gate: 서버 환경파일의 명시적 flag로 제어함
- 수동 제출: Vercel 대시보드 버튼이 GitHub Actions를 거쳐 등록 IP 서버에서 실행함
- 공개 결과 갱신: `src/public_results.py` 결과 JSON 변경 시 GitHub Actions `Publish public results`가 Lightsail publish를 실행함
- Discord 알림: 실제 제출 성공 건이 있을 때만 발송하며 양팀 선발투수를 포함함

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

## 모델 해석

feature importance와 SHAP 분석은 `src/feature_analysis.py`가 담당함.

생성 산출물:

- LightGBM gain/split feature importance CSV 및 Top N bar plot
- SHAP summary plot, SHAP mean absolute impact bar plot, CSV
- 선택 feature별 SHAP dependence plot
- permutation importance CSV 및 bar plot
- 웹 공개용 `web/public/feature-analysis/manifest.json`

실행 예시:

```bash
uv run --python 3.12 python scripts/evaluate_model.py \
  --model-version lgbm_v008 \
  --years 2023,2024,2025 \
  --feature-analysis \
  --publish-web \
  --top-n 30
```

로컬 분석 산출물은 `outputs/feature_analysis/<model_version>/`에 저장함.
`--publish-web`을 함께 쓰면 `web/public/feature-analysis/`에 PNG/CSV/manifest를 복사해 Vercel 공개 페이지가 읽을 수 있게 함.

주의:

- feature importance와 SHAP importance는 인과관계가 아님
- “이 feature가 원인이다”가 아니라 “모델이 이 feature를 예측에 강하게 활용했다”로 해석해야 함
- LightGBM gain/split importance와 SHAP 기여도는 서로 다른 관점임

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

대회 제출 API는 Postman 검증과 동일하게 `multipart/form-data` text field로 전송함.

```text
s_no=20260330
percent=48
```

제출 정책:

- `STATIZ_MIN_LEAD_MINUTES=35`: 경기 시작 35분 전보다 이른 제출 후보 제외
- T-20 이후: 자동 제출 제외
- T-15 이후: 공식 deadline 기준 제출 금지
- 라인업 없음: 제출 가능 window 안에서는 fallback 예측 후보 처리
- 중복 제출 방지: 자동 제출은 `source=auto` 성공 이력을 기준으로 같은 경기 반복 제출을 막음. 수동 제출 성공은 이후 자동 갱신 1회를 막지 않음
- Discord 알림: 실제 제출 성공 건만 알림

Discord 성공 알림 예시:

```text
- 18:30 KIA vs LG: LG 승률 57.12% (제출 홈팀 승률 57.12%) / 선발 네일 vs 임찬규
- 17:00 한화 vs 삼성: 한화 승률 55.60% (제출 홈팀 승률 44.40%) / 선발 류현진 vs 후라도
```

## 공개 대시보드

Next.js 앱은 `web/` 기준으로 Vercel에 배포함.

- 메인 타이틀: `Y-wins KBO Forecast`
- 데이터 파일: `web/public/results.json`
- favicon: `web/app/icon.png`
- Submitted games: 제출된 경기의 submitted probability 공개
- 경기 카드: 제출일 기준 페이지네이션, `M.D` 날짜 표기, 팀 matchup 중앙 배치, 선발투수는 각 팀 확률 아래 표시
- Finalized ledger: final/cancelled 경기만 날짜별 페이지네이션 표시
- Feature analysis: `web/public/feature-analysis/manifest.json` 기반 모델 해석 차트와 CSV 링크 표시
- Model guide: 모델 target, feature family, naming rule, 상위 SHAP feature 설명 표시
- 언어 토글: 기본 영어 UI, 우상단 버튼으로 한국어/영어 전환 및 브라우저 저장
- Hit/Miss/Accuracy: 실제 제출 확률인 `submitted_prob` 기준 계산
- Cancelled: 정확도 계산에서 제외, 카드/ledger 결과는 `Cancelled`로 표시
- 운영 패널 game date: `YYYY.MM.DD` 형식 표시

수동 제출 버튼은 Vercel API route가 GitHub Actions workflow dispatch를 호출하고, workflow가 등록 IP 서버에서 제출 스크립트를 실행하는 구조임. 대회 제출 API는 브라우저/Vercel에서 직접 호출하지 않음.

## 서버 운영

systemd unit:

- `ops/systemd/statiz-auto-submit.service`
- `ops/systemd/statiz-auto-submit.timer`
- `ops/systemd/statiz-public-results.service`
- `ops/systemd/statiz-public-results.timer`

서버 wrapper:

- `scripts/server_auto_submit.sh`
- `scripts/server_manual_submit.sh`
- `scripts/server_publish_public_results.sh`
- `scripts/server_update.sh`

서버 환경파일은 배포 환경별 private runbook에서 관리함.

```bash
STATIZ_ENV_FILE=/path/to/statiz-auto-submit.env
```

실제 제출 gate는 아래 세 값이 모두 제출 허용 상태일 때만 열린다.

```bash
STATIZ_DRY_RUN_ONLY=<0_or_1>
STATIZ_EXECUTE_SUBMIT=<0_or_1>
STATIZ_IP_REGISTERED=<0_or_1>
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

해당 날짜의 schedule/boxscore/lineup raw 파일을 다시 받아 최종 점수까지 갱신:

```bash
uv run python -m src.main collect --year 2026 --date 2026-06-11 --force-refresh
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

모델 해석 산출물 생성 및 웹 공개 파일 갱신:

```bash
uv run --python 3.12 python scripts/evaluate_model.py \
  --model-version lgbm_v008 \
  --years 2023,2024,2025 \
  --feature-analysis \
  --publish-web
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
├── feature_analysis.py # feature importance/SHAP/permutation 분석
└── public_results.py   # 공개 대시보드 JSON export

ops/systemd/            # server systemd unit
scripts/                # 평가 및 서버 운영 스크립트
docs/                   # 설계/운영 문서
web/                    # Vercel 공개 대시보드
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
