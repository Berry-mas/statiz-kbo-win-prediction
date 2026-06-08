# API 연동 및 제출 규칙 정리

## 1. 대회 운영상 반드시 지켜야 할 규칙
이 대회는 데이터 수집과 제출을 모두 JSON 형식 API로 통일한다.
즉, 파일 업로드 방식이나 수동 입력이 아니라, 반드시 API 호출 기반으로 운영해야 한다.

핵심 규칙:
- 모든 분석 데이터는 JSON API로 수신
- 예측 결과도 JSON API로 제출
- 지정 API 방식 외 제출은 인정되지 않음
- 사전 등록된 IP를 통해서만 접근 가능
- 경기 시작 15분 전까지 제출 완료해야 함
- 1개월 단위 제출률 70% 미만이면 API 차단 및 참가 자격 박탈 가능
- 1분 동안 일정량 이상 반복 제출 시 block 3분 가능
- 제출 확률은 홈팀 기준 승리 확률
- 소수점 둘째 자리까지 제출
- 50.00%는 실패 처리

---

## 2. 운영에 필요한 내부 API/모듈
대회 외부 API와 별개로, 우리 프로젝트 내부에서도 아래 인터페이스를 분리해 두는 것이 좋다.

### 2.1 collector API
역할:
- 대회 API에서 일정, 팀, 선수, 기록, 라인업 데이터 수집
- raw DB 적재

예시 함수:
- `fetch_schedule(date)`
- `fetch_game_detail(game_id)`
- `fetch_lineup(game_id)`
- `fetch_team_stats(date)`
- `fetch_pitcher_stats(date)`

### 2.2 feature API
역할:
- raw/clean 데이터를 받아 feature 테이블 생성

예시 함수:
- `build_features_for_training(start_date, end_date)`
- `build_features_for_game(game_id, as_of_time)`

### 2.3 inference API
역할:
- feature를 입력받아 홈팀 승률 예측

예시 함수:
- `predict_game(game_id)`
- `predict_games(game_ids)`

반환 예시:
```json
{
  "game_id": 2026041801,
  "home_win_probability": 54.37,
  "model_version": "lgbm_v001",
  "feature_version": "fgm_v003"
}
```

### 2.4 submission API
역할:
- 대회 제출 API로 전송
- 응답 저장
- 재시도 및 결과 검증

예시 함수:
- `submit_prediction(game_id, home_win_probability)`
- `verify_submission(game_id)`

### 2.5 monitoring API
역할:
- 제출 누락 감지
- 제출률 계산
- 차단 위험 감시

예시 함수:
- `check_missing_submissions(date)`
- `calc_monthly_submission_rate(month)`
- `alert_if_deadline_near(game_id)`

---

## 3. 내부 REST 예시
실제로 FastAPI 등을 붙인다면 아래처럼 나눌 수 있다.

### POST /v1/features/games/{game_id}
특정 경기 feature 생성

### POST /v1/inference/games/{game_id}
특정 경기 예측 생성

응답:
```json
{
  "game_id": "2026041801",
  "home_win_probability": 54.37,
  "rounded_probability": 54.37,
  "ready_for_submission": true
}
```

### POST /v1/submissions/games/{game_id}
대회 API 제출 실행

응답:
```json
{
  "game_id": "2026041801",
  "submitted": true,
  "submitted_probability": 54.37,
  "submitted_at": "2026-04-18T17:31:22+09:00",
  "provider_response_status": "success"
}
```

### GET /v1/submissions/games/{game_id}
제출 결과 조회

### GET /v1/health
서비스 상태 확인

---

## 4. 제출 직전 검증 규칙
제출 전에 반드시 아래를 검사한다.

- [ ] game_id 존재 여부
- [ ] 경기 취소 여부
- [ ] 마감 시각 15분 전 이전인지
- [ ] 확률이 0~100 범위인지
- [ ] 소수점 둘째 자리 반올림 적용 여부
- [ ] 반올림 결과가 50.00인지
- [ ] 동일 경기 중복 제출 정책 확인
- [ ] API 응답 성공 여부 저장
- [ ] 개인 페이지 기록값과 대조 여부

권장 보정 로직 예시:
```python
def normalize_prob(p: float) -> float:
    p = max(0.01, min(99.99, p))
    p = round(p, 2)
    if p == 50.00:
        p = 50.01
    return p
```

---

## 5. 재시도 정책
대회 서버나 네트워크 이슈를 고려해 재시도 정책을 둔다.

권장:
- 타임아웃: 짧게 설정
- exponential backoff 적용
- 단, 마감 15분 규정 때문에 너무 늦게 재시도하지 않기
- 모든 실패는 로그 + 알림 전송

예시:
- 1차 실패: 즉시 재시도
- 2차 실패: 10초 후
- 3차 실패: 30초 후
- 이후 사람 확인 또는 fallback

---

## 6. 로그 설계
최소 아래 로그는 남겨야 한다.

- 수집 요청 로그
- 수집 응답 로그
- feature 생성 로그
- 모델 추론 로그
- 제출 요청 payload
- 제출 응답 payload
- 제출 성공 여부
- 최종 참가자 페이지 대조 결과

권장 테이블:
- `prediction_log`
- `submission_log`
- `submission_verification_log`

---

## 7. 실전 체크리스트
경기 당일 운영 체크리스트

### 경기 전
- [ ] 오늘 경기 목록 확보
- [ ] 선발 정보 확보
- [ ] 라인업 공개 감지
- [ ] feature 생성 성공
- [ ] 예측 확률 생성 성공
- [ ] 50.00 회피 적용
- [ ] 제출 성공
- [ ] 참가자 페이지 값 대조

### 주간 점검
- [ ] 제출 누락 경기 확인
- [ ] 월간 제출률 확인
- [ ] API 호출량 이상 여부 확인
- [ ] 고정 IP 상태 점검
- [ ] 모델 드리프트 및 최근 성능 점검
