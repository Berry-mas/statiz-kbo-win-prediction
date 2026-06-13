# 고정 IP 서버 이전 기록

## 결정

로컬 Mac에서 dry-run 자동화, Discord 알림, 공개 대시보드를 검증한 뒤 고정 공인 IP가 있는 서버로 운영을 이전했다.

2026-06-10 기준 서버 이전은 Lightsail로 완료했다.

- Ubuntu 24.04
- SSH user: `ubuntu`
- repo path: `/home/ubuntu/statiz_code`
- static IP: `3.39.52.227`
- 기준 코드: GitHub `origin/main` 최신 운영 커밋
- `data/`, `artifacts/`, `.env` 배치 완료
- systemd timer/service 설치 완료
- 대회측 IP 등록 완료
- 실제 제출 gate 해제 완료

이유:

- 로컬 Mac은 절전, 재부팅, 네트워크 변경, 외출 시 IP 변경 리스크가 있다.
- 대회 API는 등록 IP에서만 호출할 수 있다.
- Vercel 대시보드는 대회 API를 호출하지 않으므로 등록 IP 서버일 필요가 없다.

## 목표 아키텍처

```text
고정 IP 서버
  - Statiz API 수집
  - 라인업 폴링
  - 모델 예측
  - dry-run / 실제 제출
  - Discord 알림
  - public results.json 생성
  - GitHub push 또는 배포용 sync

Vercel / Next.js
  - public results.json 읽기
  - 확정 경기 결과만 공개 표시
  - Statiz API 호출 없음
  - API key / secret 없음
```

## 서버 후보 검토 기록

우선순위:

1. AWS Lightsail + Static IP
2. AWS EC2 + Elastic IP
3. Naver Cloud VM + 공인 고정 IP
4. Oracle Cloud VM + Reserved Public IP

MVP 이전은 AWS Lightsail로 진행했다.

## 이전 전 로컬 완료 조건 기록

- `auto-submit --skip-collect --skip-features --now ...` 리허설 통과
- T-20 이전: `ready` 또는 `lineup_missing_fallback`
- T-20 이후, T-15 이전: `past_safe_cutoff`
- T-15 이후: `past_hard_deadline`
- Discord 알림 수신 확인
- `web/public/results.json` 생성 확인
- `uv run poe all` 통과

## 서버 준비 체크리스트 기록

1. 서버 생성
   - Ubuntu LTS 사용
   - 고정 공인 IP 연결
   - SSH key 기반 접속

2. 대회측 등록
   - 서버 고정 공인 IP 확인
   - 해당 IP를 Statiz 대회측에 등록 또는 기존 등록 IP 교체 요청
   - 등록 완료 후 실제 제출 gate 해제

3. 런타임 설치
   - Python 3.11+
   - uv
   - git
   - Node.js는 서버에서 대시보드를 빌드하지 않는다면 필수 아님

4. repo 배치
   - GitHub에서 repo clone
   - `uv sync`
   - `.env` 생성
   - `data/`, `artifacts/`는 공개 repo에 없으므로 별도 전송 또는 재생성

5. secret 설정
   - `API_KEY`
   - `API_SECRET`
   - `DISCORD_WEBHOOK_URL`
   - request delay / timeout env

6. dry-run 검증
   - `--skip-collect --skip-features --now ...`로 deadline 리허설
   - 실제 날짜 dry-run
   - Discord 알림 확인

7. 실제 제출 gate
   - 서버 IP가 대회측 등록 IP와 일치
   - `--execute-submit` 없이 dry-run 성공
   - `logs/scheduler_run_log.csv` status 확인
   - `prediction/savePrediction` payload 확인

## 운영 명령 예시

API 호출 없이 deadline 정책만 리허설:

```bash
uv run python -m src.main auto-submit \
  --date 2025-10-01 \
  --model-version lgbm_v008 \
  --skip-collect \
  --skip-features \
  --now 2025-10-01T17:30:00+09:00
```

실제 경기일 dry-run:

```bash
uv run python -m src.main auto-submit \
  --date YYYY-MM-DD \
  --model-version lgbm_v008
```

실제 제출:

```bash
uv run python -m src.main auto-submit \
  --date YYYY-MM-DD \
  --model-version lgbm_v008 \
  --execute-submit
```

## 남은 운영 개선 후보

- public JSON과 제출 로그의 공개 가능 subset을 더 자세히 배포
- 서버 health check와 Discord heartbeat 추가
- 웹 대시보드에서 수동 제출 workflow 상태 표시

서버 systemd 운영 절차는 `docs/08_lightsail_server_operations.md`에 정리한다.
