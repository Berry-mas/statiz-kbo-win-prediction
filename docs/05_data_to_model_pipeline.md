# 데이터 수집 → 피처 엔지니어링 → 모델 학습 파이프라인

> 전체 흐름은 `statiz_prediction_using.xlsx` (16개 시트) 와 `docs/02~03` 문서를 기반으로 구현됨.

---

## 1. 전체 흐름 요약

```
Statiz API
    │
    ▼ (1단계) 수집
data/raw/{year}/{type}/*.json        ← 원본 JSON 그대로 저장
    │
    ▼ (2단계) 정제
data/clean/*.csv                     ← 정형화된 테이블
    │
    ▼ (3단계) 피처 생성
data/features/feature_game_pre_match_{year}.csv   ← 경기 1행 = 입력 벡터
    │
    ▼ (4단계) 학습
artifacts/model_registry/lgbm_v{N}/  ← LightGBM 모델 5 seeds
    │
    ▼ (5단계) 추론 + 제출
POST /prediction/savePrediction       ← 홈팀 승률 % 제출
```

---

## 2. 1단계: 데이터 수집 (`src/collector.py`)

### 호출하는 API (엑셀 `00_INDEX`, `API_CODE` 시트 기반)

| API | 엔드포인트 | 저장 경로 | 주요 파라미터 |
|-----|-----------|-----------|--------------|
| 경기 일정 | `GET /prediction/gameSchedule` | `raw/{year}/schedule/{YYYY-MM-DD}.json` | year, month, day |
| 박스스코어 | `GET /prediction/gameBoxscore` | `raw/{year}/boxscore/{s_no}.json` | s_no |
| 라인업 | `GET /prediction/gameLineup` | `raw/{year}/lineup/{s_no}.json` | s_no |
| 팀 타격 기록 | `GET /prediction/teamRecord` | `raw/{year}/team_stats/{year}_all_batting.json` | m2=batting, year |
| 팀 투구 기록 | `GET /prediction/teamRecord` | `raw/{year}/team_stats/{year}_all_pitching.json` | m2=pitching, year |
| 선수 일별 기록 | `GET /prediction/playerDay` | `raw/{year}/player_day/{p_no}_{year}.json` | p_no, year |
| 선수 시즌 기록 | `GET /prediction/playerSeason` | `raw/{year}/player_season/{p_no}.json` | p_no |
| 선수 상황별 기록 | `GET /prediction/playerSituation` | `raw/{year}/player_situation/{p_no}_{year}_2.json` | p_no, year, si=2(구장별) |
| 날짜별 로스터 | `GET /prediction/playerRoster` | `raw/{year}/roster/{date}_{t_code}.json` | date, code=1(1군), t_code |

### 핵심 설계 원칙
- **멱등성**: 파일이 이미 있으면 API 미호출 (스킵)
- **`_collected_at`**: 수집 시각을 모든 JSON에 추가 저장
- 정규시즌(`leagueType=10100`) 경기만 처리

---

## 3. 2단계: 정제 (`src/cleaner.py`)

raw JSON → clean CSV 변환. 4개 테이블 생성.

### 3.1 `games.csv`
**소스**: `raw/{year}/schedule/*.json` → `data["date"]` 리스트

| 컬럼 | 설명 | 원본 필드 |
|------|------|----------|
| s_no | 경기 번호 | `s_no` |
| game_date | YYYY-MM-DD | year+month+day 조합 |
| game_time | 경기 시작 시각 | `hm` |
| stadium_code | 구장 코드 | `s_code` |
| home_team_code | 홈팀 코드 | `homeTeam` |
| away_team_code | 원정팀 코드 | `awayTeam` |
| home_score / away_score | 최종 점수 | `homeScore`, `awayScore` |
| game_state | 경기 상태 (1=전/3=종료/4=취소) | `s_state` |
| game_type | 1=정규/2=더블헤더1차/3=더블헤더2차 | `gameType` |
| is_cancelled | 취소 여부 | game_state==4 |
| **target_home_win** | **정답 레이블** | home_score > away_score → 1.0, < → 0.0, 취소/무 → NaN |

### 3.2 `lineup_snapshot.csv`
**소스**: `raw/{year}/lineup/*.json` → `data["t_cdoe"]` 리스트 (API 오타 그대로)

| 컬럼 | 설명 | 원본 필드 |
|------|------|----------|
| s_no | 경기 번호 | `s_no` |
| team_code | 팀 코드 | `t_code` |
| p_no | 선수 번호 | `p_no` |
| batting_order | 타순 (투수=0) | `battingOrder` |
| position_code | 포지션 (1=투수) | `position` |
| is_starter | 선발 여부 | `starting=="Y"` |
| is_pitcher | 투수 여부 | `position==1` |

### 3.3 `team_daily_snapshot.csv`
**소스**: `raw/{year}/team_stats/{year}_all_batting.json` + `_pitching.json`

| 컬럼 | 설명 | 원본 필드 |
|------|------|----------|
| biz_date | 기준일 | 수집 실행일 |
| team_code | 팀 코드 | `t_code` |
| ops_season | 팀 시즌 OPS | `OPS` |
| woba_season | 팀 시즌 wOBA | `wOBA` |
| wrc_plus_season | 팀 시즌 wRC+ | `wRCPlus` |
| avg_season / obp_season / slg_season | 타율/출루율/장타율 | `AVG`, `OBP`, `SLG` |
| era_season | 팀 시즌 ERA | `ERA` |
| fip_season | 팀 시즌 FIP | `FIP` |
| whip_season | 팀 시즌 WHIP | `WHIP` |
| rra9pf_season | 구장보정 RA9 | `rRA9pf` |

### 3.4 `starter_daily_snapshot.csv`
**소스**: `raw/{year}/player_day/{p_no}_{year}.json` + `player_season/{p_no}.json`

| 컬럼 | 설명 | 계산 방법 |
|------|------|----------|
| era_season / fip_season / whip_season | 시즌 누적 | playerSeason `ERA`, `FIP`, `WHIP` |
| rra9pf_season | 구장보정 RA9 | playerSeason `rRA9pf` |
| era_last_3 | 최근 3선발 ERA | playerDay 최근 3경기 IP 가중 평균 |
| fip_last_3 | 최근 3선발 FIP | playerDay 최근 3경기 단순 평균 |
| ip_last_3 / np_last_3 | 최근 3경기 이닝/투구수 | playerDay 합산 |
| days_rest | 직전 등판 이후 휴식일 | biz_date - 직전 등판 날짜 |
| last_game_np | 직전 경기 투구수 | playerDay 가장 최근 `NP` |

> IP 변환: `7.1` → `7 + 1/3 = 7.333` (이닝.아웃 형식 보정)

### 3.5 `bullpen_daily_snapshot.csv`
**소스**: 팀별 전체 불펜 투수(GS=0) 의 playerDay 3일치 집계

| 컬럼 | 설명 |
|------|------|
| bullpen_era_last_3 | 최근 3일 불펜 ERA (IP 가중) |
| bullpen_fip_last_3 | 최근 3일 불펜 FIP (단순 평균) |
| bullpen_ip_last_3 | 최근 3일 불펜 소화 이닝 합계 |
| bullpen_np_last_3 | 최근 3일 불펜 총 투구수 |
| back_to_back_count | 전전날 + 전날 모두 등판한 투수 수 |

---

## 4. 3단계: 피처 생성 (`src/feature_builder.py`)

clean CSV → `feature_game_pre_match_{year}.csv`. **경기 1행 = 모델 입력 1행**.

### 누출 방지 규칙 (CRITICAL)
> 모든 피처는 `biz_date < game_date` (경기 날짜 이전) 데이터만 사용.
> 같은 날 경기 결과가 rolling에 포함되지 않도록 strict `<` 비교.

### 피처 컬럼 전체 목록

#### 식별자 (모델 입력 제외)
| 컬럼 | 설명 |
|------|------|
| s_no | 경기 번호 |
| game_date | 경기 날짜 |
| year | 연도 |
| home_starter_p_no / away_starter_p_no | 선발 투수 번호 (식별용) |

#### 팀 시즌 누적 지표 (12개)
| 피처 | 설명 | 원천 |
|------|------|------|
| home/away_ops_season | 홈/원정팀 시즌 OPS | team_daily_snapshot |
| home/away_woba_season | 시즌 wOBA | team_daily_snapshot |
| home/away_wrc_plus_season | 시즌 wRC+ | team_daily_snapshot |
| home/away_era_season | 팀 시즌 ERA | team_daily_snapshot |
| home/away_fip_season | 팀 시즌 FIP | team_daily_snapshot |
| home/away_whip_season | 팀 시즌 WHIP | team_daily_snapshot |

#### 최근 흐름 (4개)
| 피처 | 설명 |
|------|------|
| home/away_win_rate_last_5 | 직전 5경기 승률 (games.csv 롤링) |
| home/away_wins_last_5 | 직전 5경기 승리 수 |

#### 선발 투수 (14개)
| 피처 | 설명 | 원천 |
|------|------|------|
| home/away_starter_era_season | 선발 투수 시즌 ERA | starter_daily_snapshot |
| home/away_starter_fip_season | 선발 투수 시즌 FIP | starter_daily_snapshot |
| home/away_starter_whip_season | 선발 투수 시즌 WHIP | starter_daily_snapshot |
| home/away_starter_era_last_3 | 최근 3선발 ERA | starter_daily_snapshot |
| home/away_starter_fip_last_3 | 최근 3선발 FIP | starter_daily_snapshot |
| home/away_starter_days_rest | 휴식일 수 | starter_daily_snapshot |
| home/away_starter_np_last_game | 직전 등판 투구수 | starter_daily_snapshot |

#### 불펜 상태 (4개)
| 피처 | 설명 | 원천 |
|------|------|------|
| home/away_bullpen_era_last_3 | 불펜 최근 3일 ERA | bullpen_daily_snapshot |
| home/away_bullpen_ip_last_3 | 불펜 최근 3일 이닝 | bullpen_daily_snapshot |

#### 컨텍스트 (5개)
| 피처 | 설명 | 값 |
|------|------|-----|
| stadium_code | 구장 코드 (파크팩터 proxy) | 범주형 |
| day_of_week | 요일 (0=월~6=일) | 0~6 |
| month | 월 | 3~10 |
| is_doubleheader | 더블헤더 여부 | True/False |
| home/away_game_number | 시즌 누적 경기 수 | 정수 |

#### 정답 레이블
| 컬럼 | 값 |
|------|-----|
| target_home_win | 1.0=홈 승, 0.0=홈 패, NaN=취소/무승부/미완료 (학습 제외) |

---

## 5. 4단계: 모델 학습 (`src/trainer.py`)

### 모델
- **LightGBM** binary classification
- **앙상블**: seed 5개(42, 123, 456, 789, 1337) 모델 평균

### 연도별 데이터 분리
```
2023 데이터 → feature_game_pre_match_2023.csv  (~720경기)
2024 데이터 → feature_game_pre_match_2024.csv  (~720경기)
2025 데이터 → feature_game_pre_match_2025.csv  (~720경기)

학습 예시: --years 2023,2024 --val-years 2025
```

### 시간 기반 교차검증 (Time-based CV)
```
Fold 1: 3~4월 학습  → 5월 검증
Fold 2: 3~5월 학습  → 6월 검증
Fold 3: 3~6월 학습  → 7월 검증
Fold 4: 3~7월 학습  → 8월 검증
Fold 5: 3~8월 학습  → 9월 검증
```
> 미래 데이터 누출 없음 (expanding window)

### 하이퍼파라미터
```python
objective        = "binary"
metric           = "binary_logloss"
num_leaves       = 31
learning_rate    = 0.05
feature_fraction = 0.8
bagging_fraction = 0.8
bagging_freq     = 5
min_child_samples = 20
early_stopping_rounds = 50
```

### 범주형 피처
`home_team_code`, `away_team_code`, `stadium_code`, `day_of_week`, `month`, `is_doubleheader`

### 평가 지표
- **LogLoss** (primary): 확률 예측 품질
- **Brier Score** (secondary): 예측 오차 제곱 평균

### 저장 아티팩트
```
artifacts/model_registry/lgbm_v001/
├── model_seed0.txt ~ model_seed4.txt  ← LightGBM 텍스트 포맷
├── feature_list.json                  ← 입력 피처 목록
├── categorical_features.json          ← 범주형 피처 목록
├── metrics.json                       ← fold별 LogLoss, Brier
└── train_config.yaml                  ← 학습 설정
```

---

## 6. 5단계: 추론 + 제출

### 확률 보정 (`normalize_prob`)
```python
p = max(0.01, min(99.99, p))   # 범위 클리핑
p = round(p, 2)                 # 소수 둘째 자리
if p == 50.00:
    p = 50.01                   # 50.00% 금지 (대회 규칙)
```

### 제출 API
```
POST /prediction/savePrediction
Body: { "s_no": 2025041801, "percent": 54.37 }
```

### 재시도 정책
- 1회: 즉시
- 2회: 10초 후
- 3회: 30초 후
- 전부 실패: 로그 기록

### 제출 로그 (`logs/submission_log.csv`)
| 컬럼 | 내용 |
|------|------|
| s_no | 경기 번호 |
| submitted_prob | 제출한 확률 |
| submitted | 성공 여부 |
| attempts | 시도 횟수 |
| response_message | API 응답 메시지 |

---

## 7. 현재 구현 vs 미구현 피처

### 구현됨 ✅
- 팀 시즌 OPS / wOBA / wRC+ / ERA / FIP / WHIP
- 최근 5경기 승률
- 선발 투수 시즌 + 최근 3선발 ERA / FIP / 휴식일 / 직전 투구수
- 불펜 최근 3일 ERA / 이닝
- 선발 라인업 전년도 OPS / wOBA / wRC+ / WAR 집계
- 구장 코드, 요일, 월, 더블헤더

### 미구현 (확장 후보) ⬜
- 선수 구장별 스플릿 (`playerSituation`, si=2)
- 선발 라인업 최근 5경기 OPS
- 홈/원정 split 지표 (teamRecord ha=H/N 파라미터 활용)
- 리그 평균 대비 z-score
- 전 시즌 가중 이동평균
