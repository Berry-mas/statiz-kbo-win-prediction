import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

type TopFeature = {
  feature: string;
  value: number;
};

type AnalysisManifest = {
  generated_at: string;
  model_version: string | null;
  sample_size: number;
  years?: number[];
  analysis_window?: {
    type: string;
    start_date?: string;
    sample_size: number;
  };
  top_features?: {
    shap?: TopFeature[];
  };
};

type FeatureFamily = {
  id: string;
  title: string;
  titleKo: string;
  description: string;
  descriptionKo: string;
  examples: string[];
};

type ModelFact = {
  label: string;
  labelKo: string;
  value: string;
  valueKo: string;
  detail: string;
  detailKo: string;
};

type PipelineStep = {
  label: string;
  labelKo: string;
  href?: string;
};

const MANIFEST_FILE = path.join(
  process.cwd(),
  "public",
  "feature-analysis",
  "manifest.json",
);

const PIPELINE_STEPS: PipelineStep[] = [
  { label: "Schedule", labelKo: "일정" },
  { label: "Team stats", labelKo: "팀 지표", href: "/team-stats" },
  { label: "Lineup", labelKo: "라인업", href: "/lineup" },
  { label: "LightGBM", labelKo: "LightGBM", href: "/lightgbm" },
  { label: "Probability", labelKo: "확률" },
];

const FEATURE_FAMILIES: FeatureFamily[] = [
  {
    id: "starter",
    title: "Starter quality",
    titleKo: "선발 투수",
    description:
      "Starting pitcher run prevention, traffic prevention, workload, and recent pitching form.",
    descriptionKo: "선발 투수의 실점 억제, 출루 허용, 투구 부담, 최근 등판 흐름.",
    examples: ["starter era", "starter whip", "starter fip proxy", "starter np last game"],
  },
  {
    id: "lineup",
    title: "Lineup strength",
    titleKo: "라인업 공격력",
    description:
      "Expected offensive quality from listed batters using previous season and lineup-weighted stats.",
    descriptionKo: "예상 선발 타자의 이전 시즌 성적과 라인업 가중 공격 지표.",
    examples: ["lineup prev pa sum", "lineup prev war", "top4 ops", "lineup coverage"],
  },
  {
    id: "bullpen",
    title: "Bullpen load",
    titleKo: "불펜 부담",
    description:
      "Recent bullpen usage and availability signals, especially innings thrown in the previous games.",
    descriptionKo: "최근 불펜 사용량과 가용성 신호, 특히 직전 경기들의 투구 이닝.",
    examples: ["bullpen ip last 3", "home minus away bullpen load"],
  },
  {
    id: "recent_form",
    title: "Recent form",
    titleKo: "최근 흐름",
    description:
      "Short-window team performance signals such as recent win rate and recent run differential.",
    descriptionKo: "최근 승률, 최근 득실 차이처럼 짧은 구간의 팀 경기력 신호.",
    examples: ["win rate last 5", "run diff last 5", "team recent win rate ratio"],
  },
  {
    id: "team_context",
    title: "Team context",
    titleKo: "팀 맥락",
    description:
      "Season-level team strength, scoring environment, team identity, and broad matchup context.",
    descriptionKo: "시즌 단위 팀 전력, 득점 환경, 팀 정체성, 전반적인 매치업 맥락.",
    examples: ["runs for pg", "runs against pg", "team code", "games played"],
  },
  {
    id: "schedule",
    title: "Schedule",
    titleKo: "일정",
    description:
      "Calendar and schedule context that can capture systematic day or timing effects.",
    descriptionKo: "요일이나 일정 효과를 포착할 수 있는 캘린더/스케줄 맥락.",
    examples: ["day of week"],
  },
];

export const dynamic = "force-static";

export default async function ModelGuidePage() {
  const manifest = await loadManifest();
  const topFeatures = manifest?.top_features?.shap?.slice(0, 16) ?? [];
  const facts = buildModelFacts(manifest);

  return (
    <main className="dashboard-shell">
      <section className="feature-page-heading">
        <div>
          <p className="eyebrow" data-en="Model guide" data-ko="모델 설명">
            Model guide
          </p>
          <h1 data-en="Model & feature guide" data-ko="모델/변수 설명">
            Model & feature guide
          </h1>
        </div>
        <div className="page-actions">
          <a className="quiet-link" data-en="Dashboard" data-ko="대시보드" href="/">
            Dashboard
          </a>
          <a
            className="quiet-link"
            data-en="Feature analysis"
            data-ko="Feature 분석"
            href="/feature-analysis"
          >
            Feature analysis
          </a>
        </div>
      </section>

      <section className="guide-intro-panel">
        <div>
          <p
            className="eyebrow"
            data-en="What the model predicts"
            data-ko="모델 예측 대상"
          >
            What the model predicts
          </p>
          <h2
            data-en="Home-team win probability before first pitch"
            data-ko="경기 시작 전 홈팀 승리 확률"
          >
            Home-team win probability before first pitch
          </h2>
          <p
            data-en="The public model produces a probability from 0% to 100%. Values above 50% lean toward the home team; values below 50% lean toward the away team."
            data-ko="공개 모델은 0%부터 100%까지의 확률을 산출함. 50%보다 높으면 홈팀 쪽, 50%보다 낮으면 원정팀 쪽 예측임."
          >
            The public model produces a probability from 0% to 100%. Values above
            50% lean toward the home team; values below 50% lean toward the away
            team.
          </p>
        </div>
        <div className="guide-flow" aria-label="Model pipeline">
          {PIPELINE_STEPS.map((step) =>
            step.href ? (
              <a
                className="guide-flow-link"
                data-en={step.label}
                data-ko={step.labelKo}
                href={step.href}
                key={step.label}
              >
                {step.label}
              </a>
            ) : (
              <span
                className="guide-flow-static"
                data-en={step.label}
                data-ko={step.labelKo}
                key={step.label}
              >
                {step.label}
              </span>
            ),
          )}
        </div>
      </section>

      <section className="metric-grid" aria-label="Model guide facts">
        {facts.map((fact) => (
          <article className="metric-card" key={fact.label}>
            <span data-en={fact.label} data-ko={fact.labelKo}>
              {fact.label}
            </span>
            <strong data-en={fact.value} data-ko={fact.valueKo}>
              {fact.value}
            </strong>
            <p data-en={fact.detail} data-ko={fact.detailKo}>
              {fact.detail}
            </p>
          </article>
        ))}
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Feature families" data-ko="변수 묶음">
              Feature families
            </p>
            <p
              data-en="Variables are grouped by the baseball context they describe."
              data-ko="변수는 설명하는 야구 맥락에 따라 묶임."
            >
              Variables are grouped by the baseball context they describe.
            </p>
          </div>
        </div>
        <div className="guide-family-grid">
          {FEATURE_FAMILIES.map((family) => (
            <article className="guide-family-card" key={family.id}>
              <strong data-en={family.title} data-ko={family.titleKo}>
                {family.title}
              </strong>
              <p data-en={family.description} data-ko={family.descriptionKo}>
                {family.description}
              </p>
              <div>
                {family.examples.map((example) => (
                  <span key={example}>{example}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Naming convention" data-ko="변수 이름 규칙">
              Naming convention
            </p>
            <p
              data-en="Feature names encode side, comparison direction, and time window."
              data-ko="변수 이름에는 팀 방향, 비교 방향, 시간 구간이 들어감."
            >
              Feature names encode side, comparison direction, and time window.
            </p>
          </div>
        </div>
        <div className="guide-rule-grid">
          <GuideRule
            body="A feature measured for the home team."
            bodyKo="홈팀 기준으로 측정한 변수."
            prefix="home_"
          />
          <GuideRule
            body="A feature measured for the away team."
            bodyKo="원정팀 기준으로 측정한 변수."
            prefix="away_"
          />
          <GuideRule
            body="Home value minus away value. Positive values favor the home side for that raw signal."
            bodyKo="홈팀 값에서 원정팀 값을 뺀 변수. 원값 기준 양수면 홈팀 쪽 신호가 더 큼."
            prefix="home_minus_away_"
          />
          <GuideRule
            body="Previous-season player or lineup statistic used before the current game."
            bodyKo="경기 전 사용할 수 있는 이전 시즌 선수/라인업 통계."
            prefix="prev"
          />
          <GuideRule
            body="Recent rolling window over the previous 3 or 5 games."
            bodyKo="직전 3경기 또는 5경기 기준 최근 흐름."
            prefix="last_3 / last_5"
          />
          <GuideRule
            body="Approximation derived from available public stat fields when the exact advanced metric is not directly present."
            bodyKo="정확한 고급 지표가 없을 때 공개 통계로 만든 근사 지표."
            prefix="proxy"
          />
        </div>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p
              className="eyebrow"
              data-en="Current top SHAP features"
              data-ko="현재 상위 SHAP 변수"
            >
              Current top SHAP features
            </p>
            <p
              data-en="Latest published features with plain-language descriptions."
              data-ko="최근 게시된 상위 변수를 쉬운 설명과 함께 표시함."
            >
              Latest published features with plain-language descriptions.
            </p>
          </div>
          <span className="network-count">
            {topFeatures.length}{" "}
            <span data-en="features" data-ko="변수">
              features
            </span>
          </span>
        </div>
        {topFeatures.length > 0 ? (
          <div className="guide-feature-table-wrap">
            <table className="guide-feature-table">
              <thead>
                <tr>
                  <th data-en="Feature" data-ko="변수">Feature</th>
                  <th data-en="Family" data-ko="묶음">Family</th>
                  <th data-en="Direction" data-ko="방향">Direction</th>
                  <th data-en="Meaning" data-ko="의미">Meaning</th>
                  <th>Mean |SHAP|</th>
                </tr>
              </thead>
              <tbody>
                {topFeatures.map((feature) => {
                  const description = describeFeature(feature.feature);
                  return (
                    <tr key={feature.feature}>
                      <td>
                        <strong>{feature.feature}</strong>
                      </td>
                      <td data-en={description.family} data-ko={description.familyKo}>
                        {description.family}
                      </td>
                      <td data-en={description.direction} data-ko={description.directionKo}>
                        {description.direction}
                      </td>
                      <td data-en={description.meaning} data-ko={description.meaningKo}>
                        {description.meaning}
                      </td>
                      <td className="score">{feature.value.toFixed(5)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div
            className="empty-state"
            data-en="Publish feature analysis artifacts to show the current top feature table."
            data-ko="현재 상위 변수 표를 보려면 feature analysis 산출물을 게시해야 함."
          >
            Publish feature analysis artifacts to show the current top feature table.
          </div>
        )}
      </section>

      <section className="feature-note">
        <strong data-en="Interpretation guardrail" data-ko="해석 주의사항">
          Interpretation guardrail
        </strong>
        <p
          data-en="These variables explain model behavior, not causality. SHAP and importance values say which signals the model used strongly for prediction; they do not prove why a team won."
          data-ko="이 변수들은 모델의 행동을 설명할 뿐 인과관계를 뜻하지 않음. SHAP과 중요도 값은 모델이 예측에 강하게 사용한 신호를 보여주며, 특정 팀이 왜 이겼는지를 증명하지 않음."
        >
          These variables explain model behavior, not causality. SHAP and
          importance values say which signals the model used strongly for
          prediction; they do not prove why a team won.
        </p>
      </section>
    </main>
  );
}

function GuideRule({
  prefix,
  body,
  bodyKo,
}: {
  prefix: string;
  body: string;
  bodyKo: string;
}) {
  return (
    <article className="guide-rule-card">
      <strong>{prefix}</strong>
      <p data-en={body} data-ko={bodyKo}>
        {body}
      </p>
    </article>
  );
}

async function loadManifest(): Promise<AnalysisManifest | null> {
  if (!existsSync(MANIFEST_FILE)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(MANIFEST_FILE, "utf8")) as unknown;
  if (!isManifest(parsed)) {
    return null;
  }
  return parsed;
}

function isManifest(value: unknown): value is AnalysisManifest {
  return (
    isRecord(value) &&
    typeof value.generated_at === "string" &&
    typeof value.sample_size === "number"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function buildModelFacts(manifest: AnalysisManifest | null): ModelFact[] {
  return [
    {
      label: "Model",
      labelKo: "모델",
      value: manifest?.model_version ?? "n/a",
      valueKo: manifest?.model_version ?? "n/a",
      detail: "LightGBM ensemble from the saved model registry",
      detailKo: "저장된 모델 레지스트리의 LightGBM 앙상블",
    },
    {
      label: "Target",
      labelKo: "예측 대상",
      value: "Home win",
      valueKo: "홈 승",
      detail: "Binary classification probability for the home side",
      detailKo: "홈팀 승리 여부를 예측하는 이진 분류 확률",
    },
    {
      label: "Analysis sample",
      labelKo: "분석 샘플",
      value: manifest ? String(manifest.sample_size) : "n/a",
      valueKo: manifest ? String(manifest.sample_size) : "n/a",
      detail: formatWindowLabels(manifest?.analysis_window).en,
      detailKo: formatWindowLabels(manifest?.analysis_window).ko,
    },
    {
      label: "Training years",
      labelKo: "학습 연도",
      value: manifest?.years?.join(", ") ?? "n/a",
      valueKo: manifest?.years?.join(", ") ?? "n/a",
      detail: "Feature rows loaded for evaluation and analysis",
      detailKo: "평가와 분석에 로드된 feature 행 기준",
    },
  ];
}

function formatWindowLabels(window?: AnalysisManifest["analysis_window"]): {
  en: string;
  ko: string;
} {
  if (!window) {
    return {
      en: "Feature analysis artifact not published",
      ko: "Feature 분석 산출물이 아직 게시되지 않음",
    };
  }
  if (window.start_date) {
    if (window.type === "late_2025_analysis_sample") {
      return {
        en: `2025 late-season holdout from ${window.start_date}`,
        ko: `2025년 후반 검증 구간, ${window.start_date} 이후`,
      };
    }
    return {
      en: `${window.type} from ${window.start_date}`,
      ko: `${window.type}, ${window.start_date} 이후`,
    };
  }
  return { en: window.type, ko: window.type };
}

function describeFeature(feature: string): {
  family: string;
  familyKo: string;
  direction: string;
  directionKo: string;
  meaning: string;
  meaningKo: string;
} {
  const family = featureFamily(feature);
  const direction = featureDirection(feature);
  const meaning = featureMeaning(feature);
  return {
    family: family.en,
    familyKo: family.ko,
    direction: direction.en,
    directionKo: direction.ko,
    meaning: meaning.en,
    meaningKo: meaning.ko,
  };
}

function featureFamily(feature: string): { en: string; ko: string } {
  const value = feature.toLowerCase();
  if (value.includes("starter")) {
    return { en: "Starter quality", ko: "선발 투수" };
  }
  if (
    value.includes("lineup") ||
    ["ops", "woba", "wrcplus", "war", "pa_sum", "sb_sum", "hr_sum"].some((token) =>
      value.includes(token),
    )
  ) {
    return { en: "Lineup strength", ko: "라인업 공격력" };
  }
  if (value.includes("bullpen")) {
    return { en: "Bullpen load", ko: "불펜 부담" };
  }
  if (value.includes("last_5") || value.includes("recent")) {
    return { en: "Recent form", ko: "최근 흐름" };
  }
  if (
    ["run_diff", "runs_for", "runs_against", "win_rate", "team_code", "games_played"].some(
      (token) => value.includes(token),
    )
  ) {
    return { en: "Team context", ko: "팀 맥락" };
  }
  if (value.includes("day_of_week")) {
    return { en: "Schedule", ko: "일정" };
  }
  return { en: "Other signal", ko: "기타 신호" };
}

function featureDirection(feature: string): { en: string; ko: string } {
  if (feature.startsWith("home_minus_away_")) {
    return { en: "Home minus away", ko: "홈-원정 비교" };
  }
  if (feature.startsWith("home_")) {
    return { en: "Home side", ko: "홈팀 기준" };
  }
  if (feature.startsWith("away_")) {
    return { en: "Away side", ko: "원정팀 기준" };
  }
  return { en: "Shared context", ko: "공통 맥락" };
}

function featureMeaning(feature: string): { en: string; ko: string } {
  const cleaned = feature
    .replace(/^home_minus_away_/, "")
    .replace(/^home_/, "")
    .replace(/^away_/, "");
  const parts: string[] = [];
  const partsKo: string[] = [];

  if (cleaned.includes("starter")) {
    parts.push("starting pitcher signal");
    partsKo.push("선발 투수 신호");
  }
  if (cleaned.includes("lineup")) {
    parts.push("projected batting lineup signal");
    partsKo.push("예상 타순 신호");
  }
  if (cleaned.includes("bullpen")) {
    parts.push("recent bullpen workload signal");
    partsKo.push("최근 불펜 부담 신호");
  }
  if (cleaned.includes("era")) {
    parts.push("earned runs allowed per nine innings");
    partsKo.push("9이닝당 자책점 허용");
  }
  if (cleaned.includes("whip")) {
    parts.push("walks plus hits allowed per inning");
    partsKo.push("이닝당 볼넷과 안타 허용");
  }
  if (cleaned.includes("fip_proxy")) {
    parts.push("fielding-independent pitching approximation");
    partsKo.push("수비 무관 투구 지표 근사값");
  }
  if (cleaned.includes("np_last_game")) {
    parts.push("pitch count from the previous appearance");
    partsKo.push("직전 등판 투구 수");
  }
  if (cleaned.includes("pa_sum")) {
    parts.push("lineup plate appearance volume");
    partsKo.push("라인업 타석 수 규모");
  }
  if (cleaned.includes("ops")) {
    parts.push("on-base plus slugging quality");
    partsKo.push("출루율과 장타율 기반 공격력");
  }
  if (cleaned.includes("woba")) {
    parts.push("weighted on-base quality");
    partsKo.push("가중 출루 기반 공격력");
  }
  if (cleaned.includes("wrcplus")) {
    parts.push("run creation indexed to league context");
    partsKo.push("리그 맥락을 반영한 득점 생산력");
  }
  if (cleaned.includes("war")) {
    parts.push("wins-above-replacement contribution");
    partsKo.push("대체선수 대비 기여도");
  }
  if (cleaned.includes("sb_sum")) {
    parts.push("stolen-base volume");
    partsKo.push("도루 규모");
  }
  if (cleaned.includes("stats_coverage")) {
    parts.push("share of lineup with usable previous stats");
    partsKo.push("이전 통계가 있는 라인업 비율");
  }
  if (cleaned.includes("run_diff")) {
    parts.push("recent scoring margin");
    partsKo.push("최근 득실 차이");
  }
  if (cleaned.includes("win_rate")) {
    parts.push("recent or season win-rate strength");
    partsKo.push("최근 또는 시즌 승률 신호");
  }
  if (cleaned.includes("runs_for")) {
    parts.push("team runs scored per game");
    partsKo.push("팀 경기당 득점");
  }
  if (cleaned.includes("runs_against")) {
    parts.push("team runs allowed per game");
    partsKo.push("팀 경기당 실점");
  }
  if (cleaned.includes("team_code")) {
    parts.push("team identity categorical signal");
    partsKo.push("팀 정체성 범주형 신호");
  }
  if (cleaned.includes("day_of_week")) {
    parts.push("calendar context");
    partsKo.push("요일/일정 맥락");
  }
  if (cleaned.includes("last_3")) {
    parts.push("computed over the last 3 games");
    partsKo.push("최근 3경기 기준");
  }
  if (cleaned.includes("last_5")) {
    parts.push("computed over the last 5 games");
    partsKo.push("최근 5경기 기준");
  }
  if (cleaned.includes("prev")) {
    parts.push("based on previous-season player stats");
    partsKo.push("이전 시즌 선수 통계 기반");
  }

  if (parts.length === 0) {
    const fallback = cleaned.replaceAll("_", " ");
    return { en: fallback, ko: fallback };
  }
  return {
    en: sentenceCase(parts.join("; ")),
    ko: `${partsKo.join("; ")}.`,
  };
}

function sentenceCase(value: string): string {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}.`;
}
