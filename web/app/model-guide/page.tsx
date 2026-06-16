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
  description: string;
  examples: string[];
};

type ModelFact = {
  label: string;
  value: string;
  detail: string;
};

const MANIFEST_FILE = path.join(
  process.cwd(),
  "public",
  "feature-analysis",
  "manifest.json",
);

const FEATURE_FAMILIES: FeatureFamily[] = [
  {
    id: "starter",
    title: "Starter quality",
    description:
      "Starting pitcher run prevention, traffic prevention, workload, and recent pitching form.",
    examples: ["starter era", "starter whip", "starter fip proxy", "starter np last game"],
  },
  {
    id: "lineup",
    title: "Lineup strength",
    description:
      "Expected offensive quality from listed batters using previous season and lineup-weighted stats.",
    examples: ["lineup prev pa sum", "lineup prev war", "top4 ops", "lineup coverage"],
  },
  {
    id: "bullpen",
    title: "Bullpen load",
    description:
      "Recent bullpen usage and availability signals, especially innings thrown in the previous games.",
    examples: ["bullpen ip last 3", "home minus away bullpen load"],
  },
  {
    id: "recent_form",
    title: "Recent form",
    description:
      "Short-window team performance signals such as recent win rate and recent run differential.",
    examples: ["win rate last 5", "run diff last 5", "team recent win rate ratio"],
  },
  {
    id: "team_context",
    title: "Team context",
    description:
      "Season-level team strength, scoring environment, team identity, and broad matchup context.",
    examples: ["runs for pg", "runs against pg", "team code", "games played"],
  },
  {
    id: "schedule",
    title: "Schedule",
    description:
      "Calendar and schedule context that can capture systematic day or timing effects.",
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
          <p className="eyebrow">Model guide</p>
          <h1>Model & feature guide</h1>
        </div>
        <div className="page-actions">
          <a className="quiet-link" href="/">
            Dashboard
          </a>
          <a className="quiet-link" href="/feature-analysis">
            Feature analysis
          </a>
        </div>
      </section>

      <section className="guide-intro-panel">
        <div>
          <p className="eyebrow">What the model predicts</p>
          <h2>Home-team win probability before first pitch</h2>
          <p>
            The public model produces a probability from 0% to 100%. Values above
            50% lean toward the home team; values below 50% lean toward the away
            team.
          </p>
        </div>
        <div className="guide-flow" aria-label="Model pipeline">
          {["Schedule", "Team stats", "Lineup", "LightGBM", "Probability"].map(
            (step) => (
              <span key={step}>{step}</span>
            ),
          )}
        </div>
      </section>

      <section className="metric-grid" aria-label="Model guide facts">
        {facts.map((fact) => (
          <article className="metric-card" key={fact.label}>
            <span>{fact.label}</span>
            <strong>{fact.value}</strong>
            <p>{fact.detail}</p>
          </article>
        ))}
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Feature families</p>
            <p>Variables are grouped by the baseball context they describe.</p>
          </div>
        </div>
        <div className="guide-family-grid">
          {FEATURE_FAMILIES.map((family) => (
            <article className="guide-family-card" key={family.id}>
              <strong>{family.title}</strong>
              <p>{family.description}</p>
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
            <p className="eyebrow">Naming convention</p>
            <p>Feature names encode side, comparison direction, and time window.</p>
          </div>
        </div>
        <div className="guide-rule-grid">
          <GuideRule prefix="home_" body="A feature measured for the home team." />
          <GuideRule prefix="away_" body="A feature measured for the away team." />
          <GuideRule
            prefix="home_minus_away_"
            body="Home value minus away value. Positive values favor the home side for that raw signal."
          />
          <GuideRule
            prefix="prev"
            body="Previous-season player or lineup statistic used before the current game."
          />
          <GuideRule
            prefix="last_3 / last_5"
            body="Recent rolling window over the previous 3 or 5 games."
          />
          <GuideRule
            prefix="proxy"
            body="Approximation derived from available public stat fields when the exact advanced metric is not directly present."
          />
        </div>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Current top SHAP features</p>
            <p>Latest published features with plain-language descriptions.</p>
          </div>
          <span className="network-count">{topFeatures.length} features</span>
        </div>
        {topFeatures.length > 0 ? (
          <div className="guide-feature-table-wrap">
            <table className="guide-feature-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Family</th>
                  <th>Direction</th>
                  <th>Meaning</th>
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
                      <td>{description.family}</td>
                      <td>{description.direction}</td>
                      <td>{description.meaning}</td>
                      <td className="score">{feature.value.toFixed(5)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">
            Publish feature analysis artifacts to show the current top feature table.
          </div>
        )}
      </section>

      <section className="feature-note">
        <strong>Interpretation guardrail</strong>
        <p>
          These variables explain model behavior, not causality. SHAP and
          importance values say which signals the model used strongly for
          prediction; they do not prove why a team won.
        </p>
      </section>
    </main>
  );
}

function GuideRule({ prefix, body }: { prefix: string; body: string }) {
  return (
    <article className="guide-rule-card">
      <strong>{prefix}</strong>
      <p>{body}</p>
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
      value: manifest?.model_version ?? "n/a",
      detail: "LightGBM ensemble from the saved model registry",
    },
    {
      label: "Target",
      value: "Home win",
      detail: "Binary classification probability for the home side",
    },
    {
      label: "Analysis sample",
      value: manifest ? String(manifest.sample_size) : "n/a",
      detail: formatWindow(manifest?.analysis_window),
    },
    {
      label: "Training years",
      value: manifest?.years?.join(", ") ?? "n/a",
      detail: "Feature rows loaded for evaluation and analysis",
    },
  ];
}

function formatWindow(window?: AnalysisManifest["analysis_window"]): string {
  if (!window) {
    return "Feature analysis artifact not published";
  }
  if (window.start_date) {
    return `${window.type} from ${window.start_date}`;
  }
  return window.type;
}

function describeFeature(feature: string): {
  family: string;
  direction: string;
  meaning: string;
} {
  return {
    family: featureFamily(feature),
    direction: featureDirection(feature),
    meaning: featureMeaning(feature),
  };
}

function featureFamily(feature: string): string {
  const value = feature.toLowerCase();
  if (value.includes("starter")) {
    return "Starter quality";
  }
  if (
    value.includes("lineup") ||
    ["ops", "woba", "wrcplus", "war", "pa_sum", "sb_sum", "hr_sum"].some((token) =>
      value.includes(token),
    )
  ) {
    return "Lineup strength";
  }
  if (value.includes("bullpen")) {
    return "Bullpen load";
  }
  if (value.includes("last_5") || value.includes("recent")) {
    return "Recent form";
  }
  if (
    ["run_diff", "runs_for", "runs_against", "win_rate", "team_code", "games_played"].some(
      (token) => value.includes(token),
    )
  ) {
    return "Team context";
  }
  if (value.includes("day_of_week")) {
    return "Schedule";
  }
  return "Other signal";
}

function featureDirection(feature: string): string {
  if (feature.startsWith("home_minus_away_")) {
    return "Home minus away";
  }
  if (feature.startsWith("home_")) {
    return "Home side";
  }
  if (feature.startsWith("away_")) {
    return "Away side";
  }
  return "Shared context";
}

function featureMeaning(feature: string): string {
  const cleaned = feature
    .replace(/^home_minus_away_/, "")
    .replace(/^home_/, "")
    .replace(/^away_/, "");
  const parts: string[] = [];

  if (cleaned.includes("starter")) {
    parts.push("starting pitcher signal");
  }
  if (cleaned.includes("lineup")) {
    parts.push("projected batting lineup signal");
  }
  if (cleaned.includes("bullpen")) {
    parts.push("recent bullpen workload signal");
  }
  if (cleaned.includes("era")) {
    parts.push("earned runs allowed per nine innings");
  }
  if (cleaned.includes("whip")) {
    parts.push("walks plus hits allowed per inning");
  }
  if (cleaned.includes("fip_proxy")) {
    parts.push("fielding-independent pitching approximation");
  }
  if (cleaned.includes("np_last_game")) {
    parts.push("pitch count from the previous appearance");
  }
  if (cleaned.includes("pa_sum")) {
    parts.push("lineup plate appearance volume");
  }
  if (cleaned.includes("ops")) {
    parts.push("on-base plus slugging quality");
  }
  if (cleaned.includes("woba")) {
    parts.push("weighted on-base quality");
  }
  if (cleaned.includes("wrcplus")) {
    parts.push("run creation indexed to league context");
  }
  if (cleaned.includes("war")) {
    parts.push("wins-above-replacement contribution");
  }
  if (cleaned.includes("sb_sum")) {
    parts.push("stolen-base volume");
  }
  if (cleaned.includes("stats_coverage")) {
    parts.push("share of lineup with usable previous stats");
  }
  if (cleaned.includes("run_diff")) {
    parts.push("recent scoring margin");
  }
  if (cleaned.includes("win_rate")) {
    parts.push("recent or season win-rate strength");
  }
  if (cleaned.includes("runs_for")) {
    parts.push("team runs scored per game");
  }
  if (cleaned.includes("runs_against")) {
    parts.push("team runs allowed per game");
  }
  if (cleaned.includes("team_code")) {
    parts.push("team identity categorical signal");
  }
  if (cleaned.includes("day_of_week")) {
    parts.push("calendar context");
  }
  if (cleaned.includes("last_3")) {
    parts.push("computed over the last 3 games");
  }
  if (cleaned.includes("last_5")) {
    parts.push("computed over the last 5 games");
  }
  if (cleaned.includes("prev")) {
    parts.push("based on previous-season player stats");
  }

  if (parts.length === 0) {
    return cleaned.replaceAll("_", " ");
  }
  return sentenceCase(parts.join("; "));
}

function sentenceCase(value: string): string {
  return `${value.charAt(0).toUpperCase()}${value.slice(1)}.`;
}
