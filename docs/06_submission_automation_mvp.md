# 제출 자동화 dry-run MVP

## 목표

등록 IP 환경의 로컬 머신에서 날짜/시간 기준 제출 자동화를 검증한다.
MVP 기본값은 dry-run이며, 실제 대회 제출 API는 호출하지 않는다.

## 확정 정책

- 대회 API 호출 위치: 등록 IP가 보장되는 로컬 머신
- 웹 대시보드: Next.js/Vercel 공개 페이지
- 웹 대시보드 데이터: 경기 종료 후 실제 결과가 확정된 제출 경기만 공개
- 알림: Discord webhook
- 제출 안전 cutoff: 경기 공식 시작 20분 전
- 공식 hard deadline: 경기 공식 시작 15분 전
- T-20까지 라인업 없음: fallback 예측 제출 대상으로 처리
- 라인업 누락 기록: `lineup_missing=True`, status `lineup_missing_fallback`

## dry-run 동작

```bash
uv run python -m src.main auto-submit --date YYYY-MM-DD --model-version lgbm_v008
```

기본 실행 흐름:

1. 당일 raw 데이터 수집
2. clean CSV 재생성
3. feature CSV 재생성
4. 모델 예측 생성
5. 제출 eligibility 판단
6. 실제 `prediction/savePrediction` 호출은 생략
7. `logs/scheduler_run_log.csv`에 제출 예정 payload 기록
8. `web/public/results.json` 공개용 결과 JSON 생성
9. Discord 요약 알림 전송

실제 제출은 아래 플래그를 명시한 경우에만 실행한다.

```bash
uv run python -m src.main auto-submit --date YYYY-MM-DD --model-version lgbm_v008 --execute-submit
```

과거 경기일로 T-20/T-15 정책을 리허설할 때는 `--now`를 사용한다.

```bash
uv run python -m src.main auto-submit \
  --date 2025-10-01 \
  --model-version lgbm_v008 \
  --skip-collect \
  --skip-features \
  --now 2025-10-01T17:30:00+09:00
```

`--now` 값이 timezone 없이 들어오면 KST로 해석한다. `Z` 또는 `+09:00`처럼 timezone이 있는 ISO timestamp는 KST로 변환해 deadline 판단에 사용한다.

systemd처럼 반복 실행되는 운영 환경에서는 너무 이른 제출 후보를 막기 위해 `--min-lead-minutes`를 함께 쓴다.

```bash
uv run python -m src.main auto-submit \
  --date YYYY-MM-DD \
  --model-version lgbm_v008 \
  --min-lead-minutes 35
```

이 설정에서는 경기 시작 35분 전보다 이른 실행은 status `too_early`로 기록되고 제출 후보에서 제외된다.
경기 시작 T-35부터 T-20 안전 cutoff 전까지만 `ready` 또는 `lineup_missing_fallback`이 제출 후보가 된다.

## 로그

| 파일 | 목적 |
| --- | --- |
| `logs/prediction_log.csv` | 모델 예측 결과 |
| `logs/submission_log.csv` | 실제 제출 결과 |
| `logs/scheduler_run_log.csv` | 스케줄러 판단, dry-run payload, 라인업 누락 여부 |
| `web/public/results.json` | 공개 웹 대시보드용 확정 결과 |

`logs/`, `data/`, `artifacts/`, `.env`는 공개 repo에 올리지 않는다.

실제 제출 모드에서는 `logs/submission_log.csv`에 이미 `submitted=True`로 기록된 동일 날짜/동일 `s_no` 경기를 다시 제출하지 않는다.

## 공개 JSON 제한

`web/public/results.json`은 아래 조건을 모두 만족하는 경기만 포함한다.

- clean games row가 존재한다.
- `game_state == 3`
- 홈/원정 점수가 있다.
- `target_home_win`이 있다.
- 실제 제출 로그에서 `submitted=True`인 row가 있다.

진행 중 경기, 경기 전 경기, 취소 경기, dry-run 전용 payload, API 응답 원문은 공개하지 않는다.

## 열린 질문

- Discord 외 별도 장애 알림 채널이 필요한지
- public dashboard를 DB 기반으로 확장할 시점

## 운영 방침

로컬 Mac은 MVP 검증용으로 사용한다. 실제 시즌 운영 전에는 고정 공인 IP가 붙은 서버로 이전하고, 그 서버 IP를 대회측에 등록한다.

상세 이전 계획은 `docs/07_local_to_static_ip_server_plan.md`를 따른다.
Lightsail 운영 자동화 절차는 `docs/08_lightsail_server_operations.md`를 따른다.
