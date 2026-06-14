# 고정 IP 서버 운영 자동화

## 현재 운영 상태

- 서버: 고정 IP Linux 서버
- repo path: 배포 환경별 private runbook에서 관리
- static IP: 공개 문서에 기록하지 않음
- 기준 코드: GitHub `origin/main` 최신 운영 커밋
- `data/`, `artifacts/` 전송 완료
- `.env` 설정 완료
- systemd timer/service 설치 완료
- 실제 제출 gate는 서버 환경파일의 명시적 flag로 제어
- Vercel 수동 제출 버튼은 GitHub Actions SSH를 통해 등록 IP 서버에서 실행됨

## 안전 원칙

실제 제출은 dry-run 해제, execute-submit 허용, 등록 IP 확인 flag가 모두 제출 허용 상태일 때만 wrapper가 `--execute-submit`을 붙인다.

현재 운영값은 private runbook 또는 서버 환경파일에서만 확인한다.

## 서버 환경파일

서버에서 `STATIZ_ENV_FILE` 경로의 환경파일을 생성한다.

```bash
sudo tee "$STATIZ_ENV_FILE" >/dev/null <<'EOF'
STATIZ_REPO_DIR=/path/to/statiz_code
STATIZ_UV_BIN=/path/to/uv
STATIZ_MODEL_VERSION=lgbm_v008
STATIZ_DRY_RUN_ONLY=<0_or_1>
STATIZ_EXECUTE_SUBMIT=<0_or_1>
STATIZ_IP_REGISTERED=<0_or_1>
STATIZ_MIN_LEAD_MINUTES=35
STATIZ_SKIP_COLLECT=<0_or_1>
STATIZ_SKIP_FEATURES=<0_or_1>
STATIZ_PUBLISH_PUBLIC_RESULTS=<0_or_1>
STATIZ_PUBLISH_UPDATE_BEFORE=1
EOF
```

`STATIZ_MIN_LEAD_MINUTES=35`이면 경기 시작 35분 전부터 T-20 안전 cutoff 전까지만 제출 후보가 된다.
수동 제출은 `scripts/server_manual_submit.sh`를 사용하며 `STATIZ_MIN_LEAD_MINUTES` 대기 조건을 붙이지 않는다. 공식 T-15 마감 검증은 동일하게 유지된다.
제출 API는 Postman 검증과 동일하게 `multipart/form-data` text field `s_no`, `percent`로 호출한다.

## systemd 설치

repo의 unit 파일을 systemd 경로에 복사한다.
서버 timezone은 `Asia/Seoul`이어야 한다.

```bash
cd "$STATIZ_REPO_DIR"
timedatectl show -p Timezone --value
sudo cp ops/systemd/statiz-auto-submit.service /etc/systemd/system/
sudo cp ops/systemd/statiz-auto-submit.timer /etc/systemd/system/
sudo cp ops/systemd/statiz-public-results.service /etc/systemd/system/
sudo cp ops/systemd/statiz-public-results.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now statiz-auto-submit.timer
sudo systemctl enable --now statiz-public-results.timer
```

수동 dry-run 1회 실행:

```bash
sudo systemctl start statiz-auto-submit.service
```

상태와 로그 확인:

```bash
systemctl status statiz-auto-submit.timer
systemctl status statiz-public-results.timer
systemctl list-timers 'statiz-*'
journalctl -u statiz-auto-submit.service -n 100 --no-pager
journalctl -u statiz-public-results.service -n 100 --no-pager
tail -n 20 "$STATIZ_REPO_DIR/logs/scheduler_run_log.csv"
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

## 공개 대시보드 publish

`ops/systemd/statiz-public-results.timer`는 KST 기준 14:05, 17:05, 18:35, 23:30에 실행한다.

이 작업은 예측 제출을 하지 않는다. 해당 날짜의 schedule, boxscore, lineup raw 파일을 강제 갱신하고 clean 데이터를 다시 만든 뒤 `web/public/results.json`을 export/push한다.

14:05, 17:05, 18:35 publish는 같은 날짜 안에서 경기 시작 시간이 다른 제출 batch를 공개 대시보드에 반영하기 위한 실행이다. 정각 제출과 publish 실행이 겹치지 않도록 5분 뒤에 실행한다. 경기 전/진행 중인 제출은 제출 percent를 공개하고, Hit/Miss 결과는 경기 종료 후에만 공개한다. 23:30 publish는 경기 종료 후 최종 스코어와 공개 가능한 Hit/Miss 결과를 반영하는 기준 실행이다.

timer 파일을 수정한 뒤에는 서버의 systemd unit을 다시 설치하고 reload해야 한다.

```bash
sudo cp ops/systemd/statiz-public-results.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart statiz-public-results.timer
systemctl list-timers 'statiz-public-results.timer'
```

서버 wrapper:

```bash
./scripts/server_publish_public_results.sh
```

주요 동작:

1. `STATIZ_PUBLISH_UPDATE_BEFORE=1`이면 `scripts/server_update.sh`로 최신 `main`을 fast-forward 반영
2. `collect --force-refresh`로 해당 날짜 최종 경기 정보 재수집
3. `clean --year <year>` 실행
4. `src.public_results.export_public_results()` 실행
5. `web/public/results.json`만 변경된 경우 `origin/main`에 publish commit push

서버 checkout에 tracked local changes가 있거나 `origin/main`보다 오래된 상태면 publish는 중단된다.

## 서버 업데이트

서버에서 최신 코드를 반영할 때:

```bash
cd "$STATIZ_REPO_DIR"
STATIZ_EXPECTED_COMMIT=<expected-short-commit> ./scripts/server_update.sh
```

최신 `main`을 그대로 받을 때는 `STATIZ_EXPECTED_COMMIT`을 생략한다.

```bash
cd "$STATIZ_REPO_DIR"
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
sudoedit "$STATIZ_ENV_FILE"
```

아래처럼 변경한다.

```ini
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
```

다시 실제 제출을 열 때는 private runbook의 gate 값을 확인한 뒤 서버 환경파일에 반영한다.

변경 후에는 daemon reload 없이 다음 timer 실행부터 반영된다.
