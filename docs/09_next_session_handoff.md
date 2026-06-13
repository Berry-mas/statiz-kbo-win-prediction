# 다음 세션 핸드오프

## 현재 운영 상태

- GitHub main 최신 운영 커밋: 이 문서 작성 시점의 `origin/main`
- Lightsail: `ubuntu@3.39.52.227`
- 서버 repo: `/home/ubuntu/statiz_code`
- 실제 제출 gate: `/etc/statiz-auto-submit.env`에서 해제 완료
- 자동 제출: `statiz-auto-submit.timer`가 KST 12:30~18:30 polling
- 수동 제출: Vercel 대시보드의 `Manual Submit` 버튼이 GitHub Actions를 거쳐 Lightsail에서 실행
- 제출 API: `prediction/savePrediction`에 `multipart/form-data`로 `s_no`, `percent` 전송
- Discord: 실제 제출 성공 건만 알림. 알림에는 경기, 예측 승률, 홈팀 제출 확률, 양팀 선발투수를 포함
- 공개 웹사이트: `web/public/results.json`의 finalized submitted results만 노출

## 다음 세션에서 먼저 확인할 것

1. 수동 제출 또는 다음 자동 제출이 실제로 성공했는지 확인한다.

```bash
gh run list --repo Berry-mas/statiz-kbo-win-prediction --workflow "Manual Statiz submit" --limit 5
ssh -i /Users/junseo/Downloads/LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.39.52.227 \
  'cd /home/ubuntu/statiz_code && tail -n 20 logs/submission_log.csv'
```

2. 성공 건이 있으면 Discord 알림 문구와 선발투수 표시를 확인한다.

3. 자동 제출 후 `web/public/results.json` publish가 정상 동작했는지 확인한다.

```bash
gh run list --repo Berry-mas/statiz-kbo-win-prediction --workflow "Deploy web dashboard" --limit 5
curl -sS https://web-steel-seven-15.vercel.app/public/results.json
```

## 웹사이트 개선 아이디어

사용자 의견:
- 버튼 한 번으로 현재 얻을 수 있는 정보만으로 즉시 예측 제출하고 싶음.
- 수동 제출 후 자동 제출이 한 번 더 갱신 제출하는 구조를 원함.
- 수동 제출 Date 입력은 `YYYY-MM-DD`가 명확히 보이면 좋음.

제 의견:
- 운영 패널에 최근 수동 제출 workflow 상태를 보여주는 영역을 추가하는 것이 우선순위가 높음.
- `logs/scheduler_run_log.csv`의 오늘 경기별 상태를 공개 가능한 범위로 sanitize해서 웹에서 볼 수 있게 하면, 버튼을 누르기 전 “왜 제출 가능/불가능한지”가 명확해짐.
- 성공/실패 제출 로그를 서버 API 없이 GitHub Actions artifact 또는 public-safe JSON으로 publish하면, Vercel에서 등록 IP 문제 없이 운영 가시성을 높일 수 있음.
- 웹 버튼은 현재 token 입력 방식인데, 자주 쓸 거면 브라우저 localStorage 저장 토글을 추가할 수 있음. 단, 개인 기기에서만 쓰는 전제로 제한해야 함.
- 향후 모델 개선 후에는 dashboard에 `model_version`, 최근 N경기 accuracy, LogLoss/Brier 추이를 같이 보여주면 운영 판단에 도움이 됨.

## 모델 개선 시 주의점

- feature schema가 그대로면 서버에 새 `artifacts/model_registry/<version>`만 올리고 `STATIZ_MODEL_VERSION`을 바꾸면 됨.
- feature 컬럼이 바뀌면 코드, feature builder, predictor, artifact를 함께 배포해야 함.
- 자동 제출과 수동 제출은 같은 `STATIZ_MODEL_VERSION`을 공유함.

## 안전 체크

- 실제 제출을 멈춰야 하면 `/etc/statiz-auto-submit.env`에서 아래처럼 바꾼다.

```ini
STATIZ_DRY_RUN_ONLY=1
STATIZ_EXECUTE_SUBMIT=0
```

- 다시 열 때는 아래 세 값이 모두 맞아야 한다.

```ini
STATIZ_DRY_RUN_ONLY=0
STATIZ_EXECUTE_SUBMIT=1
STATIZ_IP_REGISTERED=1
```
