import {
  formatDateLabel,
  loadFeatureAnalysisManifest,
  type FeatureAnalysisManifest,
  type FeatureAnalysisSection,
  type TopFeature,
} from "../public-data";

type Stage = {
  title: string;
  titleKo: string;
  body: string;
  bodyKo: string;
};

const STAGES: Stage[] = [
  {
    title: "Pre-game features",
    titleKo: "경기 전 변수",
    body: "Schedule, team form, starter, bullpen, and lineup signals are frozen before first pitch.",
    bodyKo: "일정, 팀 흐름, 선발, 불펜, 라인업 신호를 경기 시작 전 기준으로 고정함.",
  },
  {
    title: "Many small trees",
    titleKo: "작은 트리 다수",
    body: "LightGBM builds many decision trees, each correcting the previous prediction errors.",
    bodyKo: "LightGBM은 여러 결정트리를 만들고 이전 예측 오차를 순차적으로 보정함.",
  },
  {
    title: "Probability output",
    titleKo: "확률 출력",
    body: "Tree scores are combined into one home-team win probability from 0% to 100%.",
    bodyKo: "트리 점수를 합쳐 0%부터 100%까지의 홈팀 승리 확률로 변환함.",
  },
];

export const dynamic = "force-static";

export default async function LightGbmPage() {
  const manifest = await loadFeatureAnalysisManifest();
  const gainSection = findSection(manifest, "lgbm_gain");
  const shapSection = findSection(manifest, "shap_bar");
  const topFeatures = (manifest?.top_features?.gain ?? []).slice(0, 8);

  return (
    <main className="dashboard-shell">
      <section className="feature-page-heading">
        <div>
          <p className="eyebrow" data-en="LightGBM" data-ko="LightGBM">
            LightGBM
          </p>
          <h1 data-en="How the model turns signals into probability" data-ko="신호를 확률로 바꾸는 방식">
            How the model turns signals into probability
          </h1>
        </div>
        <div className="page-actions">
          <a className="quiet-link" data-en="Dashboard" data-ko="대시보드" href="/">
            Dashboard
          </a>
          <a className="quiet-link" data-en="Model guide" data-ko="모델 설명" href="/model-guide">
            Model guide
          </a>
          <a className="quiet-link" data-en="Feature analysis" data-ko="Feature 분석" href="/feature-analysis">
            Feature analysis
          </a>
        </div>
      </section>

      <section className="metric-grid" aria-label="LightGBM facts">
        <article className="metric-card">
          <span data-en="Model" data-ko="모델">
            Model
          </span>
          <strong>{manifest?.model_version ?? "n/a"}</strong>
          <p data-en="Saved registry version used for public analysis" data-ko="공개 분석에 사용한 저장 모델 버전">
            Saved registry version used for public analysis
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Task" data-ko="문제 유형">
            Task
          </span>
          <strong data-en="Classification" data-ko="분류">
            Classification
          </strong>
          <p data-en="Home win versus away win" data-ko="홈 승리와 원정 승리 구분">
            Home win versus away win
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Analysis sample" data-ko="분석 샘플">
            Analysis sample
          </span>
          <strong>{manifest?.sample_size ?? "n/a"}</strong>
          <p data-en="Published feature-analysis rows" data-ko="게시된 feature-analysis 행">
            Published feature-analysis rows
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Generated" data-ko="생성일">
            Generated
          </span>
          <strong>{formatDateLabel(manifest?.generated_at ?? null)}</strong>
          <p data-en="Current public artifact timestamp" data-ko="현재 공개 산출물 기준 시각">
            Current public artifact timestamp
          </p>
        </article>
      </section>

      <section className="lightgbm-visual-panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Boosting flow" data-ko="부스팅 흐름">
              Boosting flow
            </p>
            <p
              data-en="LightGBM is a gradient-boosted tree model: small tree decisions are combined into one probability."
              data-ko="LightGBM은 gradient boosting tree 모델임. 작은 트리 판단들을 합쳐 하나의 확률을 만듦."
            >
              LightGBM is a gradient-boosted tree model: small tree decisions are combined into one probability.
            </p>
          </div>
        </div>
        <div className="boosting-flow">
          {STAGES.map((stage) => (
            <article key={stage.title}>
              <strong data-en={stage.title} data-ko={stage.titleKo}>
                {stage.title}
              </strong>
              <p data-en={stage.body} data-ko={stage.bodyKo}>
                {stage.body}
              </p>
            </article>
          ))}
        </div>
        <div className="tree-visual" aria-hidden="true">
          <div className="tree-node tree-root">feature?</div>
          <div className="tree-branch-row">
            <div className="tree-node">team form</div>
            <div className="tree-node">starter</div>
          </div>
          <div className="tree-branch-row tree-leaves">
            <div>+0.08</div>
            <div>-0.03</div>
            <div>+0.04</div>
            <div>+0.01</div>
          </div>
        </div>
      </section>

      <section className="feature-section-grid lightgbm-chart-grid">
        <FeatureChart section={gainSection} fallbackTitle="LightGBM gain importance" fallbackPath="/feature-analysis/lgbm_gain_top30.png" />
        <FeatureChart section={shapSection} fallbackTitle="SHAP mean absolute impact" fallbackPath="/feature-analysis/shap_bar_top30.png" />
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Top gain signals" data-ko="상위 gain 신호">
              Top gain signals
            </p>
            <p
              data-en="Gain means the model reduced prediction loss by splitting on that feature."
              data-ko="Gain은 해당 feature로 트리를 나눴을 때 예측 손실이 줄어든 정도를 뜻함."
            >
              Gain means the model reduced prediction loss by splitting on that feature.
            </p>
          </div>
        </div>
        <div className="top-feature-list">
          {topFeatures.map((feature) => (
            <TopFeatureRow feature={feature} key={feature.feature} />
          ))}
        </div>
      </section>

      <section className="feature-note">
        <strong data-en="Interpretation guardrail" data-ko="해석 주의사항">
          Interpretation guardrail
        </strong>
        <p
          data-en="Importance and SHAP charts describe signals the model used strongly. They do not prove that a signal caused the real game result."
          data-ko="중요도와 SHAP 차트는 모델이 강하게 활용한 신호를 설명함. 실제 경기 결과의 원인을 증명하지 않음."
        >
          Importance and SHAP charts describe signals the model used strongly. They do not prove that a signal caused the real game result.
        </p>
      </section>
    </main>
  );
}

function FeatureChart({
  section,
  fallbackTitle,
  fallbackPath,
}: {
  section: FeatureAnalysisSection | null;
  fallbackTitle: string;
  fallbackPath: string;
}) {
  const title = section?.title ?? fallbackTitle;
  const imagePath = section?.image_path ?? fallbackPath;
  const description = section?.description ?? "Published feature-analysis chart.";
  return (
    <article className="feature-figure">
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <img alt={title} src={imagePath} />
    </article>
  );
}

function TopFeatureRow({ feature }: { feature: TopFeature }) {
  return (
    <div className="top-feature-row">
      <span>{feature.feature}</span>
      <strong>{feature.value.toFixed(2)}</strong>
    </div>
  );
}

function findSection(
  manifest: FeatureAnalysisManifest | null,
  id: string,
): FeatureAnalysisSection | null {
  return manifest?.sections?.find((section) => section.id === id) ?? null;
}
