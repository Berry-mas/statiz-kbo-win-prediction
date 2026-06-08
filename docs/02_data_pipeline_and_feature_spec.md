# 데이터 파이프라인 및 피처 명세

## 1. 목표
이 문서는 스탯티즈 API로 받은 데이터를 어떻게 저장하고, 어떤 feature를 만들고, 학습 데이터셋을 어떤 기준으로 구성할지 정의한다.

계획서 기준 핵심 feature 축은 다음 네 가지다.

1. 시즌 전체 팀 전력 지표
2. 최근 흐름 지표
3. 선발 투수 영향력
4. 불펜 상태

추가로 구장 효과, 수비 지표, 홈/원정, 휴식일, 더블헤더/이동 부담 등 파생 피처를 확장 후보로 둔다.

---

## 2. 권장 데이터 계층
데이터는 아래 3계층으로 관리한다.

### 2.1 Raw Layer
API 원본 응답을 최대한 가공 없이 저장한다.

예시 테이블:
- `raw_games`
- `raw_game_lineups`
- `raw_team_daily_stats`
- `raw_pitcher_daily_stats`
- `raw_bullpen_daily_stats`
- `raw_players`
- `raw_venues`
- `raw_submission_responses`

저장 원칙:
- API 응답 원문 JSON 보관
- 수집 시각(`collected_at`) 저장
- 기준 날짜(`biz_date`) 저장
- 재수집 대비 version 또는 upsert key 관리

### 2.2 Clean Layer
분석 가능한 정형 테이블로 정리한다.

예시:
- `games`
- `team_daily_snapshot`
- `starter_daily_snapshot`
- `bullpen_daily_snapshot`
- `lineup_snapshot`

### 2.3 Feature Layer
모델 입력용 단일 테이블로 조인한다.

예시:
- `feature_game_pre_match`

이 테이블은 경기별 1행을 원칙으로 하며, 최소 아래를 포함한다.

- `game_id`
- `game_date`
- `home_team_id`
- `away_team_id`
- `target_home_win`
- 학습 시점 기준으로 누출 없는 feature 컬럼들
- 제출용 예측 컬럼
- 생성 시각 및 feature version

---

## 3. 권장 DB 테이블 초안

## 3.1 games
경기 기본 정보

주요 컬럼:
- `game_id`
- `game_date`
- `scheduled_start_time`
- `stadium_id`
- `home_team_id`
- `away_team_id`
- `status`
- `is_cancelled`
- `actual_start_time`
- `home_score`
- `away_score`

## 3.2 lineup_snapshot
라인업 공개 시점 기준 스냅샷

주요 컬럼:
- `game_id`
- `team_id`
- `player_id`
- `batting_order`
- `position_code`
- `is_starter`
- `announced_at`

## 3.3 team_daily_snapshot
팀 단위 일별 누적/최근 지표

주요 컬럼:
- `biz_date`
- `team_id`
- `ops_season`
- `woba_season`
- `wrc_plus_season`
- `era_season`
- `fip_season`
- `whip_season`
- `ops_last_5`
- `woba_last_5`
- `era_last_5`
- `fip_last_5`
- `home_split_*`
- `away_split_*`
- `stadium_split_*`

## 3.4 starter_daily_snapshot
선발 예정 투수 기준 지표

주요 컬럼:
- `biz_date`
- `pitcher_id`
- `era_season`
- `fip_season`
- `whip_season`
- `rra9pf_season`
- `pitch_count_last_game`
- `days_rest`
- `era_last_n`
- `fip_last_n`
- `stadium_split_*`

## 3.5 bullpen_daily_snapshot
불펜 소모 상태 및 최근 성과

주요 컬럼:
- `biz_date`
- `team_id`
- `bullpen_fip_last_3`
- `bullpen_whip_last_3`
- `bullpen_pitch_count_last_3`
- `bullpen_innings_last_3`
- `bullpen_back_to_back_count`
- `inherited_runner_scoring_rate`

## 3.6 feature_game_pre_match
최종 학습/추론 입력 테이블

핵심 원칙:
- 경기 시작 전에 알 수 있는 정보만 사용
- 경기 중 정보, 경기 종료 후 정보 금지
- 같은 날짜라도 경기 시작 시점 기준 누출 여부 점검

---

## 4. 피처 설계

현재 1차 구현(`feature_game_pre_match`)은 고급 Statiz as-of 지표 대신 raw/clean 데이터에서 경기 전 기준으로 재구성 가능한 피처를 우선 사용한다.

현재 구현된 주요 피처:
- 팀 시즌 누적: 경기 전 승률, 평균 득점/실점, 득실차, 경기 수
- 최근 흐름: 최근 5경기 승률, 평균 득점/실점, 득실차
- 선발투수: 경기 전 ERA, WHIP, FIP proxy, 최근 3선발 ERA/FIP proxy, 휴식일, 직전 투구수
- 불펜: 최근 3일 불펜 이닝, ERA proxy
- 상대 비교: `home_minus_away_*` 차이값
- 단순 baseline 피처: `team_win_rate_ratio`, `team_recent_win_rate_ratio`
- 결측 flag: 선발/불펜 정보 결측 여부

범주형 피처는 학습/검증/추론에서 동일한 고정 mapping을 사용한다. 팀 코드, 구장 코드, 요일, 월, 더블헤더 여부를 데이터 subset별 `cat.codes`로 다시 매핑하지 않는다.

## 4.1 시즌 전체 팀 전력
계획서 반영 기본 피처:
- 홈팀 시즌 OPS / 원정팀 시즌 OPS
- 홈팀 시즌 wOBA / 원정팀 시즌 wOBA
- 홈팀 시즌 wRC+ / 원정팀 시즌 wRC+
- 홈팀 시즌 ERA / 원정팀 시즌 ERA
- 홈팀 시즌 FIP / 원정팀 시즌 FIP
- 홈팀 시즌 WHIP / 원정팀 시즌 WHIP

추천 파생:
- 차이값: `home_metric - away_metric`
- 비율값: `home_metric / away_metric`
- 리그 평균 대비 z-score
- 홈/원정 분리 버전

## 4.2 최근 흐름
기본 창(window):
- 최근 5경기
- 비교 실험용 최근 7경기, 10경기

추천 컬럼:
- 최근 OPS, wOBA, ERA, FIP
- 최근 승률
- 최근 득점/실점 평균
- 최근 3경기와 최근 10경기 차이

## 4.3 선발 투수
기본:
- 시즌 ERA, FIP, WHIP, rRA9pf
- 최근 경기 투구 수
- 휴식일
- 최근 3경기 평균 성과
- 구장별 성과

확장:
- 상대 팀 상대 성적
- 좌/우타 상성 요약
- 전 시즌 포함 이동평균

## 4.4 불펜 상태
기본:
- 최근 3일 불펜 소화 이닝
- 최근 3일 총 투구 수
- 최근 연투 여부
- 불펜 ERA/FIP/WHIP
- 승계주자 실점률

확장:
- 필승조 사용 여부
- 전날 경기에서 고레버리지 투수 사용량
- 마무리 투수 2연투/3연투 여부

## 4.5 구장 / 환경
추천:
- 파크팩터
- 홈구장 보정 타격/투수 성과
- 돔 여부, 이동 거리, 휴식일
- 낮/밤 경기
- 더블헤더 여부

## 4.6 라인업 공개 후 피처
실전 성능에 중요할 가능성이 큼

추천:
- 선발 라인업 평균 시즌 OPS
- 선발 라인업 최근 5경기 OPS
- 중심타선 강도 지표
- 결장자 대체 수준
- 상대 선발 유형 대비 라인업 적합성

---

## 5. 누출 방지 규칙
- feature 계산 기준 시각은 항상 경기 시작 직전
- 당일 경기 결과가 포함된 누적 지표 금지
- future game 포함 rolling 금지
- 최근 n경기 계산 시 대상 경기보다 뒤의 경기 금지
- 취소 경기/서스펜디드 경기 처리 규칙 명시

---

## 6. 타깃 정의
`target_home_win`
- 홈팀 승리 시 1
- 홈팀 패배 시 0
- 무승부/취소/노게임은 학습 제외 규칙 별도 관리

---

## 7. 데이터 검증 체크리스트
- [ ] `game_id` 중복 여부
- [ ] 경기 시작 전 생성 가능한 컬럼만 존재하는지
- [ ] rolling feature가 날짜 순으로 계산되었는지
- [ ] 결측치 정책이 컬럼별로 정의되었는지
- [ ] 라인업 미공개 경기 대응 정책 존재 여부
- [ ] 제출 직전 사용할 feature와 학습 feature가 동일 스키마인지
