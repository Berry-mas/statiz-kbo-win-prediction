# Lightsail 서버 운영 자동화

## 현재 운영 상태

- 서버: AWS Lightsail, Ubuntu 24.04
- SSH user: `ubuntu`
- repo path: `/home/ubuntu/statiz_code`
- static IP: `3.39.52.227`
- 기준 코드: `95eee7f Add submission automation MVP`
- `data/`, `artifacts/` 전송 완료
- `.env` 설정 완료
- 서버 dry-run 리허설 완료
- 대회측 IP 등록 전이므로 실제 제출 금지

## 안전 원칙

등록 전 서버는 dry-run only로만 운영한다.

실제 제출은 아래 세 환경변수가 모두 맞을 때만 wrapper가 `--execute-submit`을 붙인다.

```bash
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

현재 systemd 기본값은 모두 실제 제출을 막는 값이다.

```ini
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
STATIZ_IP_REGISTERED=0
```

## 서버 환경파일

서버에서 `/etc/statiz-auto-submit.env`를 생성한다.

```bash
sudo tee /etc/statiz-auto-submit.env >/dev/null <<'EOF'
STATIZ_REPO_DIR=/home/ubuntu/statiz_code
STATIZ_UV_BIN=/home/ubuntu/.local/bin/uv
STATIZ_MODEL_VERSION=lgbm_v008
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
STATIZ_IP_REGISTERED=0
STATIZ_MIN_LEAD_MINUTES=35
STATIZ_SKIP_COLLECT=1
STATIZ_SKIP_FEATURES=1
EOF
```

`STATIZ_MIN_LEAD_MINUTES=35`이면 경기 시작 35분 전부터 T-20 안전 cutoff 전까지만 제출 후보가 된다.
등록 전 dry-run에서는 `too_early`, `ready`, `lineup_missing_fallback`, `past_safe_cutoff` 상태를 확인하는 용도다.
`STATIZ_SKIP_COLLECT=1`, `STATIZ_SKIP_FEATURES=1`은 IP 등록 전 반복 timer가 API 수집과 feature rebuild를 과하게 반복하지 않도록 하는 리허설 설정이다.

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

`ops/systemd/statiz-auto-submit.timer`는 KST 기준 13:00~18:55 사이 5분마다 실행한다.

반복 실행을 허용하는 이유:

- 등록 전에는 dry-run only라 실제 저장 API를 호출하지 않는다.
- `--min-lead-minutes 35`로 너무 이른 제출 후보를 막는다.
- IP 등록 후 실제 제출 모드에서도 `logs/submission_log.csv`의 성공 제출 이력을 보고 같은 경기 중복 제출을 건너뛴다.

## 서버 업데이트

서버에서 최신 코드를 반영할 때:

```bash
cd /home/ubuntu/statiz_code
STATIZ_EXPECTED_COMMIT=95eee7f ./scripts/server_update.sh
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

## IP 등록 후 실제 제출 전 체크

아래 조건이 모두 끝나기 전에는 `/etc/statiz-auto-submit.env`의 dry-run gate를 풀지 않는다.

- 대회측에 `3.39.52.227` 등록 완료
- 등록 완료 후 실제 경기일 dry-run 성공
- `logs/scheduler_run_log.csv`에서 제출 후보 payload 확인
- Discord dry-run 알림 수신 확인
- systemd timer와 service 로그 정상 확인

등록 완료 후 실제 제출을 열 때:

```bash
sudoedit /etc/statiz-auto-submit.env
```

아래처럼 변경한다.

```bash
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```

변경 후에는 daemon reload 없이 다음 timer 실행부터 반영된다.
