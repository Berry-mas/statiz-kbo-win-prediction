# Lightsail 서버 운영 자동화

## 현재 운영 상태

- 서버: AWS Lightsail, Ubuntu 24.04
- SSH user: `ubuntu`
- repo path: `/home/ubuntu/statiz_code`
- static IP: `3.39.52.227`
- 기준 코드: GitHub `origin/main` 최신 운영 커밋
- `data/`, `artifacts/` 전송 완료
- `.env` 설정 완료
- systemd timer/service 설치 완료
- 대회측 IP 등록 완료로 실제 제출 gate 해제 완료
- Vercel 수동 제출 버튼은 GitHub Actions SSH를 통해 이 서버에서 실행됨

## 안전 원칙

실제 제출은 아래 세 환경변수가 모두 맞을 때만 wrapper가 `--execute-submit`을 붙인다.

```bash
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

현재 운영값은 실제 제출을 허용한다.

```ini
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

## 서버 환경파일

서버에서 `/etc/statiz-auto-submit.env`를 생성한다.

```bash
sudo tee /etc/statiz-auto-submit.env >/dev/null <<'EOF'
STATIZ_REPO_DIR=/home/ubuntu/statiz_code
STATIZ_UV_BIN=/home/ubuntu/.local/bin/uv
STATIZ_MODEL_VERSION=lgbm_v008
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
STATIZ_MIN_LEAD_MINUTES=35
STATIZ_SKIP_COLLECT=0
STATIZ_SKIP_FEATURES=0
STATIZ_PUBLISH_PUBLIC_RESULTS=1
EOF
```

`STATIZ_MIN_LEAD_MINUTES=35`이면 경기 시작 35분 전부터 T-20 안전 cutoff 전까지만 제출 후보가 된다.
수동 제출은 `scripts/server_manual_submit.sh`를 사용하며 `STATIZ_MIN_LEAD_MINUTES` 대기 조건을 붙이지 않는다. 공식 T-15 마감 검증은 동일하게 유지된다.
제출 API는 Postman 검증과 동일하게 `multipart/form-data` text field `s_no`, `percent`로 호출한다.

## systemd 설치

repo의 unit 파일을 systemd 경로에 복사한다.
서버 timezone은 `Asia/Seoul`이어야 한다.

```bash
cd /home/ubuntu/statiz_code
timedatectl show -p Timezone --value
sudo cp ops/systemd/statiz-auto-submit.service /etc/systemd/system/
sudo cp ops/systemd/statiz-auto-submit.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now statiz-auto-submit.timer
```

수동 dry-run 1회 실행:

```bash
sudo systemctl start statiz-auto-submit.service
```

상태와 로그 확인:

```bash
systemctl status statiz-auto-submit.timer
systemctl list-timers 'statiz-*'
journalctl -u statiz-auto-submit.service -n 100 --no-pager
tail -n 20 /home/ubuntu/statiz_code/logs/scheduler_run_log.csv
```

## 타이머 정책

`ops/systemd/statiz-auto-submit.timer`는 KST 기준 12:30~18:30 사이 10분 단위로 polling한다.

현재 static timer는 경기 시작 시간을 직접 알지 못하고 정해진 시각에 polling한다.
주말/공휴일 14:00 경기, 17:00 경기, 18:30 경기, 경기장별 다른 시작 시간을 모두 커버하기 위해 timer window를 넓게 둔다.
`auto-submit` 내부 판단은 각 경기 row의 `game_time`을 기준으로 `STATIZ_MIN_LEAD_MINUTES`와 T-20/T-15 cutoff를 경기별로 따로 계산한다.

반복 실행을 허용하는 이유:

- `--min-lead-minutes 35`로 각 경기의 시작 시간 기준 너무 이른 제출 후보를 막는다.
- 자동 제출은 `logs/submission_log.csv`의 `source=auto` 성공 제출 이력을 보고 같은 경기 반복 제출을 건너뛴다.
- 수동 제출 성공 이력은 이후 자동 제출 갱신 1회를 막지 않는다.
- Discord 알림은 실제 제출 성공 건이 있을 때만 보내며 양팀 선발투수를 포함한다.

## 서버 업데이트

서버에서 최신 코드를 반영할 때:

```bash
cd /home/ubuntu/statiz_code
STATIZ_EXPECTED_COMMIT=<expected-short-commit> ./scripts/server_update.sh
```

최신 `main`을 그대로 받을 때는 `STATIZ_EXPECTED_COMMIT`을 생략한다.

```bash
cd /home/ubuntu/statiz_code
./scripts/server_update.sh
```

스크립트 동작:

1. `origin/main` fetch
2. tracked local changes가 있으면 중단
3. fast-forward merge
4. `uv sync --frozen`
5. `uv run python -m compileall -q src`
6. `STATIZ_UPDATE_RUN_TESTS=1`이면 `uv run pytest`

## 실제 제출 gate 변경

문제가 생겨 즉시 dry-run으로 되돌릴 때:

```bash
sudoedit /etc/statiz-auto-submit.env
```

아래처럼 변경한다.

```ini
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
```

다시 실제 제출을 열 때:

```ini
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

변경 후에는 daemon reload 없이 다음 timer 실행부터 반영된다.
