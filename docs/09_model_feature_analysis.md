# 모델 Feature Analysis 운영

## 목적

KBO 승부예측 모델이 어떤 feature를 예측에 강하게 활용하는지 공개 대시보드에서 확인하기 위한 분석 절차임.

분석 대상은 저장된 LightGBM 모델과 검증용 feature matrix임. 현재 기준 모델은 `lgbm_v008`임.

## 생성 산출물

로컬 분석 산출물:

```text
outputs/feature_analysis/<model_version>/
├─ manifest.json
├─ lgbm_feature_importance.csv
├─ lgbm_gain_top30.png
├─ lgbm_split_top30.png
├─ shap_importance.csv
├─ shap_summary.png
├─ shap_bar_top30.png
├─ permutation_importance.csv
└─ permutation_importance_top30.png
```

웹 공개 산출물:

```text
web/public/feature-analysis/
├─ manifest.json
├─ *.png
└─ *.csv
```

`/feature-analysis` 페이지는 `web/public/feature-analysis/manifest.json`을 읽어 차트와 CSV 링크를 렌더링함. manifest가 없으면 미게시 fallback 화면을 표시함.

## 실행

모델과 feature CSV가 있는 서버 checkout에서 실행함.

```bash
uv run --python 3.12 python scripts/evaluate_model.py \
  --model-version lgbm_v008 \
  --years 2023,2024,2025 \
  --feature-analysis \
  --publish-web \
  --top-n 30
```

dependence plot을 함께 만들 때:

```bash
uv run --python 3.12 python scripts/evaluate_model.py \
  --model-version lgbm_v008 \
  --years 2023,2024,2025 \
  --feature-analysis \
  --publish-web \
  --top-n 30 \
  --dependence-features home_minus_away_lineup_prev_pa_sum,away_starter_fip_proxy
```

없는 feature는 warning 후 skip함.

## 공개 반영

`--publish-web` 실행 후 생성 확인:

```bash
ls web/public/feature-analysis
```

생성 파일을 Vercel 배포 브랜치에 포함함.

```bash
git add web/public/feature-analysis
git commit -m "Publish feature analysis artifacts"
git push
```

배포 후 확인 URL:

```text
https://y-wins-kbo-forecast.vercel.app/feature-analysis
https://y-wins-kbo-forecast.vercel.app/feature-analysis/manifest.json
```

## 해석 기준

- feature importance와 SHAP importance는 인과관계가 아님
- “이 feature가 원인이다”가 아니라 “모델이 이 feature를 예측에 강하게 활용했다”로 해석함
- LightGBM gain importance는 split으로 얻은 손실 감소량 관점임
- LightGBM split importance는 tree에서 feature가 사용된 빈도 관점임
- SHAP mean absolute impact는 개별 예측에서 feature 기여도의 평균 절대값 관점임
- permutation importance는 feature를 섞었을 때 scoring이 얼마나 떨어지는지 보는 검증 데이터 기준 관점임

## 운영 주의

- `data/`, `artifacts/`, `outputs/`는 gitignore 대상임
- 웹 공개가 필요한 파일은 `web/public/feature-analysis/`만 commit함
- 분석은 late-2025 holdout row가 있으면 해당 구간을 사용하고, 없으면 로드된 전체 feature row를 사용함
- binary classification SHAP은 positive class, 즉 홈팀 승리 class 기준으로 처리함
- multi-class 모델은 현재 공개 분석 유틸의 대상이 아님
