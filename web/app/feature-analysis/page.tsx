import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

type AnalysisSection = {
  id: string;
  title: string;
  description: string;
  image_path: string | null;
  csv_path: string | null;
};

type TopFeature = {
  feature: string;
  value: number;
};

type AnalysisManifest = {
  schema_version: number;
  generated_at: string;
  model_version: string | null;
  task_type: string;
  sample_size: number;
  top_n: number;
  years?: number[];
  analysis_window?: {
    type: string;
    start_date?: string;
    sample_size: number;
  };
  interpretation_notes: string[];
  sections: AnalysisSection[];
  csv_paths: Record<string, string | null>;
  dependence_images: Record<string, string>;
  top_features: {
    gain: TopFeature[];
    split: TopFeature[];
    shap: TopFeature[];
    permutation: TopFeature[];
  };
  network_path?: string | null;
  agreement_path?: string | null;
  family_summary_path?: string | null;
  game_explanations_path?: string | null;
};

type SignalMetric = {
  rank: number;
  value: number;
};

type SignalNetworkNode = {
  id: string;
  kind: "model" | "family" | "feature";
  label: string;
  feature?: string;
  family?: string;
  family_label?: string;
  side?: string;
  score: number;
  color?: string;
  metrics?: Record<string, SignalMetric>;
};

type SignalNetworkEdge = {
  source: string;
  target: string;
  kind: "family_signal" | "family_membership" | "home_away_relation";
  weight: number;
  label: string;
};

type FeatureSignalNetwork = {
  schema_version: number;
  title: string;
  description: string;
  nodes: SignalNetworkNode[];
  edges: SignalNetworkEdge[];
};

type AgreementMethod = {
  id: string;
  label: string;
};

type AgreementRow = {
  feature: string;
  family: string;
  family_label: string;
  side: string;
  ranks: Record<string, number>;
  values: Record<string, number>;
  method_count: number;
  average_rank: number;
  consensus_score: number;
  missing_methods: string[];
};

type ImportanceAgreement = {
  schema_version: number;
  title: string;
  description: string;
  methods: AgreementMethod[];
  top_n: number;
  rows: AgreementRow[];
};

type FeatureFamilyTopFeature = {
  feature: string;
  label: string;
  side: string;
  score: number;
  ranks: Record<string, number>;
};

type FeatureFamilySummaryRow = {
  id: string;
  label: string;
  color: string;
  impact_score: number;
  impact_share: number;
  method_coverage: number;
  primary_method: string;
  feature_count: number;
  top_features: FeatureFamilyTopFeature[];
  method_scores: Record<string, number>;
};

type FeatureFamilySummary = {
  schema_version: number;
  title: string;
  description: string;
  methods: AgreementMethod[];
  top_n: number;
  families: FeatureFamilySummaryRow[];
};

type GameTeam = {
  code: number | null;
  name: string;
};

type GameExplanationFactor = {
  feature: string;
  label: string;
  family: string;
  family_label: string;
  side: string;
  contribution: number;
  abs_contribution: number;
  feature_value: number | string | null;
};

type GameExplanation = {
  id: string;
  row_index: number;
  s_no: number | null;
  game_date: string | null;
  home_team: GameTeam;
  away_team: GameTeam;
  home_win_probability: number;
  predicted_side: "home" | "away";
  actual_home_win: number | null;
  confidence: number;
  explanation_strength: number;
  top_home_factors: GameExplanationFactor[];
  top_away_factors: GameExplanationFactor[];
};

type GameExplanations = {
  schema_version: number;
  title: string;
  description: string;
  sample_size: number;
  display_count: number;
  class_label: string;
  games: GameExplanation[];
};

const MANIFEST_FILE = path.join(
  process.cwd(),
  "public",
  "feature-analysis",
  "manifest.json",
);

export const dynamic = "force-static";

export default async function FeatureAnalysisPage() {
  const manifest = await loadManifest();
  const signalNetwork = manifest
    ? await loadSignalNetwork(manifest.network_path)
    : null;
  const importanceAgreement = manifest
    ? await loadImportanceAgreement(manifest.agreement_path)
    : null;
  const familySummary = manifest
    ? await loadFeatureFamilySummary(manifest.family_summary_path)
    : null;
  const gameExplanations = manifest
    ? await loadGameExplanations(manifest.game_explanations_path)
    : null;

  return (
    <main className="dashboard-shell">
      <section className="feature-page-heading">
        <div>
          <p className="eyebrow">Model interpretation</p>
          <h1>Feature analysis</h1>
        </div>
        <a className="quiet-link" href="/">
          Dashboard
        </a>
      </section>

      {manifest ? (
        <AnalysisContent
          familySummary={familySummary}
          gameExplanations={gameExplanations}
          importanceAgreement={importanceAgreement}
          manifest={manifest}
          signalNetwork={signalNetwork}
        />
      ) : (
        <MissingAnalysisState />
      )}
    </main>
  );
}

async function loadManifest(): Promise<AnalysisManifest | null> {
  if (!existsSync(MANIFEST_FILE)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(MANIFEST_FILE, "utf8")) as unknown;
  if (!isManifest(parsed)) {
    throw new Error("Invalid feature analysis manifest.");
  }
  return parsed;
}

async function loadFeatureFamilySummary(
  summaryPath: string | null | undefined,
): Promise<FeatureFamilySummary | null> {
  if (!summaryPath?.startsWith("/feature-analysis/")) {
    return null;
  }
  const filePath = path.join(
    process.cwd(),
    "public",
    summaryPath.replace(/^\//, ""),
  );
  if (!existsSync(filePath)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  if (!isFeatureFamilySummary(parsed)) {
    throw new Error("Invalid feature family summary.");
  }
  return parsed;
}

async function loadGameExplanations(
  explanationsPath: string | null | undefined,
): Promise<GameExplanations | null> {
  if (!explanationsPath?.startsWith("/feature-analysis/")) {
    return null;
  }
  const filePath = path.join(
    process.cwd(),
    "public",
    explanationsPath.replace(/^\//, ""),
  );
  if (!existsSync(filePath)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  if (!isGameExplanations(parsed)) {
    throw new Error("Invalid game explanations.");
  }
  return parsed;
}

async function loadImportanceAgreement(
  agreementPath: string | null | undefined,
): Promise<ImportanceAgreement | null> {
  if (!agreementPath?.startsWith("/feature-analysis/")) {
    return null;
  }
  const filePath = path.join(
    process.cwd(),
    "public",
    agreementPath.replace(/^\//, ""),
  );
  if (!existsSync(filePath)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  if (!isImportanceAgreement(parsed)) {
    throw new Error("Invalid importance agreement matrix.");
  }
  return parsed;
}

async function loadSignalNetwork(
  networkPath: string | null | undefined,
): Promise<FeatureSignalNetwork | null> {
  if (!networkPath?.startsWith("/feature-analysis/")) {
    return null;
  }
  const filePath = path.join(
    process.cwd(),
    "public",
    networkPath.replace(/^\//, ""),
  );
  if (!existsSync(filePath)) {
    return null;
  }
  const parsed = JSON.parse(await readFile(filePath, "utf8")) as unknown;
  if (!isSignalNetwork(parsed)) {
    throw new Error("Invalid feature signal network.");
  }
  return parsed;
}

function AnalysisContent({
  familySummary,
  gameExplanations,
  importanceAgreement,
  manifest,
  signalNetwork,
}: {
  familySummary: FeatureFamilySummary | null;
  gameExplanations: GameExplanations | null;
  importanceAgreement: ImportanceAgreement | null;
  manifest: AnalysisManifest;
  signalNetwork: FeatureSignalNetwork | null;
}) {
  const modelVersion = manifest.model_version ?? "n/a";
  const generatedAt = formatTimestamp(manifest.generated_at);
  const dependenceEntries = Object.entries(manifest.dependence_images);

  return (
    <>
      <section className="metric-grid" aria-label="Feature analysis summary">
        <article className="metric-card">
          <span>Model</span>
          <strong>{modelVersion}</strong>
          <p>{formatYears(manifest.years)}</p>
        </article>
        <article className="metric-card">
          <span>Sample</span>
          <strong>{manifest.sample_size}</strong>
          <p>{formatWindow(manifest.analysis_window)}</p>
        </article>
        <article className="metric-card">
          <span>Generated</span>
          <strong>{generatedAt.date}</strong>
          <p>{generatedAt.time}</p>
        </article>
        <article className="metric-card">
          <span>Top N</span>
          <strong>{manifest.top_n}</strong>
          <p>{manifest.task_type}</p>
        </article>
      </section>

      <section className="feature-note">
        <strong>Interpretation guardrail</strong>
        <p>
          Feature importance and SHAP impact are not causality. Read them as the
          features the model used strongly for prediction, not as proof that a
          feature caused a win or loss.
        </p>
      </section>

      {familySummary ? <FeatureFamilySummaryPanel summary={familySummary} /> : null}

      {gameExplanations ? (
        <GameExplanationPanel explanations={gameExplanations} />
      ) : null}

      {signalNetwork ? <FeatureSignalNetworkPanel network={signalNetwork} /> : null}

      {importanceAgreement ? (
        <ImportanceAgreementPanel agreement={importanceAgreement} />
      ) : null}

      <section className="feature-section-grid">
        {manifest.sections.map((section) => (
          <article className="feature-section" key={section.id}>
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">{section.title}</p>
                <p>{section.description}</p>
              </div>
              {section.csv_path ? (
                <a className="quiet-link" href={section.csv_path}>
                  CSV
                </a>
              ) : null}
            </div>
            {section.image_path ? (
              <img alt={`${section.title} chart`} src={section.image_path} />
            ) : null}
          </article>
        ))}
      </section>

      {dependenceEntries.length > 0 ? (
        <section className="feature-section">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">SHAP dependence</p>
              <p>Selected feature-level contribution patterns.</p>
            </div>
          </div>
          <div className="feature-section-grid">
            {dependenceEntries.map(([feature, imagePath]) => (
              <figure className="feature-figure" key={feature}>
                <img alt={`${feature} dependence chart`} src={imagePath} />
                <figcaption>{feature}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}

      <section className="content-grid">
        <article className="section-panel">
          <div className="section-heading compact">
            <div>
              <p className="eyebrow">Top features</p>
            </div>
          </div>
          <TopFeatureTable rows={manifest.top_features.shap} valueLabel="Mean |SHAP|" />
        </article>

        <aside className="side-column">
          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Downloads</p>
              </div>
            </div>
            <div className="download-list">
              {Object.entries(manifest.csv_paths)
                .filter(([, href]) => Boolean(href))
                .map(([label, href]) => (
                  <a href={href ?? "#"} key={label}>
                    {formatDownloadLabel(label)}
                  </a>
                ))}
            </div>
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Method notes</p>
              </div>
            </div>
            <ul className="method-list">
              {manifest.interpretation_notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </article>
        </aside>
      </section>
    </>
  );
}

function FeatureFamilySummaryPanel({
  summary,
}: {
  summary: FeatureFamilySummary;
}) {
  const topFamilies = summary.families.slice(0, 6);
  return (
    <section className="family-summary-panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Feature family summary</p>
          <p>Aggregated model interpretation signal by baseball context.</p>
        </div>
        <span className="network-count">{summary.families.length} families</span>
      </div>
      <div className="family-card-grid">
        {topFamilies.map((family) => (
          <article className="family-card" key={family.id}>
            <div className="family-card-head">
              <span style={{ background: family.color }} />
              <div>
                <strong>{family.label}</strong>
                <p>{family.feature_count} ranked features</p>
              </div>
            </div>
            <div className="family-impact">
              <strong>{Math.round(family.impact_share * 100)}%</strong>
              <span>impact share</span>
            </div>
            <div className="family-impact-bar">
              <i
                style={{
                  background: family.color,
                  width: `${Math.max(4, Math.round(family.impact_share * 100))}%`,
                }}
              />
            </div>
            <div className="family-meta-row">
              <span>{family.method_coverage}/{summary.methods.length} methods</span>
              <span>{formatMethodLabel(family.primary_method)} led</span>
            </div>
            <div className="family-feature-list">
              {family.top_features.slice(0, 3).map((feature) => (
                <span key={feature.feature} title={feature.feature}>
                  {compactFamilyFeatureLabel(feature.label)}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function GameExplanationPanel({
  explanations,
}: {
  explanations: GameExplanations;
}) {
  const games = explanations.games.slice(0, 8);
  if (games.length === 0) {
    return null;
  }
  return (
    <section className="game-explanation-panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Game explanation view</p>
          <p>
            Per-game SHAP factors showing why the model leaned home or away for
            high-signal matchups.
          </p>
        </div>
        <span className="network-count">{explanations.display_count} games</span>
      </div>
      <div className="game-explanation-grid">
        {games.map((game) => (
          <article className="game-explanation-card" key={game.id}>
            <div className="game-explanation-head">
              <div>
                <strong>
                  {game.away_team.name} <span>at</span> {game.home_team.name}
                </strong>
                <p>{game.game_date ?? `row ${game.row_index + 1}`}</p>
              </div>
              <div className="game-explanation-probability">
                <strong>{formatProbability(game.home_win_probability)}</strong>
                <span>{game.predicted_side === "home" ? "Home lean" : "Away lean"}</span>
              </div>
            </div>
            <div className="explanation-meter" aria-hidden="true">
              <i
                className="explanation-meter-away"
                style={{ width: `${100 - game.home_win_probability * 100}%` }}
              />
              <i
                className="explanation-meter-home"
                style={{ width: `${game.home_win_probability * 100}%` }}
              />
            </div>
            <div className="game-explanation-meta">
              <span>{formatActualResult(game.actual_home_win)}</span>
              <span>{Math.round(game.confidence * 100)}% confidence</span>
              <span>{game.explanation_strength.toFixed(3)} SHAP load</span>
            </div>
            <div className="game-factor-columns">
              <GameFactorList
                factors={game.top_away_factors}
                title="Toward away"
                tone="away"
              />
              <GameFactorList
                factors={game.top_home_factors}
                title="Toward home"
                tone="home"
              />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function GameFactorList({
  factors,
  title,
  tone,
}: {
  factors: GameExplanationFactor[];
  title: string;
  tone: "away" | "home";
}) {
  return (
    <div className={`game-factor-list game-factor-list-${tone}`}>
      <span>{title}</span>
      {factors.length > 0 ? (
        factors.map((factor) => (
          <div className="game-factor" key={`${title}-${factor.feature}`}>
            <strong title={factor.feature}>{compactFamilyFeatureLabel(factor.label)}</strong>
            <small>
              {factor.family_label} / {formatContribution(factor.contribution)}
            </small>
          </div>
        ))
      ) : (
        <div className="game-factor empty">No ranked factor</div>
      )}
    </div>
  );
}

function ImportanceAgreementPanel({
  agreement,
}: {
  agreement: ImportanceAgreement;
}) {
  const strongRows = agreement.rows.filter((row) => row.method_count >= 3).length;
  return (
    <section className="agreement-panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Importance agreement</p>
          <p>
            Features that repeatedly rank high across gain, split, SHAP, and
            permutation importance.
          </p>
        </div>
        <span className="network-count">{strongRows} stable signals</span>
      </div>
      <div className="agreement-summary">
        <strong>{agreement.rows.length}</strong>
        <span>ranked features compared across {agreement.methods.length} methods</span>
      </div>
      <div className="agreement-table-wrap">
        <table className="agreement-table">
          <thead>
            <tr>
              <th>Feature</th>
              <th>Family</th>
              {agreement.methods.map((method) => (
                <th key={method.id}>{method.label}</th>
              ))}
              <th>Consensus</th>
            </tr>
          </thead>
          <tbody>
            {agreement.rows.slice(0, 18).map((row) => (
              <tr key={row.feature}>
                <td>
                  <strong>{row.feature}</strong>
                  <span>{formatFeatureSide(row.side)}</span>
                </td>
                <td>
                  <span
                    className="family-chip"
                    style={{ borderColor: familyColor(row.family) }}
                  >
                    {row.family_label}
                  </span>
                </td>
                {agreement.methods.map((method) => (
                  <td key={method.id}>
                    <AgreementRankCell
                      rank={row.ranks[method.id]}
                      topN={agreement.top_n}
                    />
                  </td>
                ))}
                <td>
                  <div className="consensus-cell">
                    <strong>{Math.round(row.consensus_score * 100)}%</strong>
                    <span>{row.method_count}/{agreement.methods.length} methods</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AgreementRankCell({
  rank,
  topN,
}: {
  rank: number | undefined;
  topN: number;
}) {
  if (!rank) {
    return <span className="agreement-rank missing">-</span>;
  }
  const intensity = Math.max(0.12, (topN - rank + 1) / topN);
  return (
    <span
      className="agreement-rank"
      style={{
        backgroundColor: `rgba(13, 122, 95, ${0.12 + intensity * 0.5})`,
      }}
    >
      #{rank}
    </span>
  );
}

function FeatureSignalNetworkPanel({ network }: { network: FeatureSignalNetwork }) {
  const layout = buildNetworkLayout(network);
  const familyNodes = network.nodes.filter((node) => node.kind === "family");
  const featureCount = network.nodes.filter((node) => node.kind === "feature").length;

  return (
    <section className="signal-network-panel">
      <div className="section-heading compact">
        <div>
          <p className="eyebrow">Feature signal network</p>
          <p>
            Top ranked model signals grouped by baseball context and connected by
            home/away relationships.
          </p>
        </div>
        <span className="network-count">{featureCount} features</span>
      </div>
      <div className="signal-network-canvas">
        <svg
          aria-label={network.title}
          role="img"
          viewBox={`0 0 ${layout.width} ${layout.height}`}
        >
          <desc>{network.description}</desc>
          {network.edges.map((edge) => {
            const source = layout.positions.get(edge.source);
            const target = layout.positions.get(edge.target);
            if (!source || !target) {
              return null;
            }
            return (
              <line
                className={`network-edge network-edge-${edge.kind}`}
                key={`${edge.source}-${edge.target}-${edge.kind}`}
                strokeWidth={edgeStrokeWidth(edge)}
                x1={source.x}
                x2={target.x}
                y1={source.y}
                y2={target.y}
              />
            );
          })}
          {network.nodes.map((node) => {
            const position = layout.positions.get(node.id);
            if (!position) {
              return null;
            }
            const radius = nodeRadius(node);
            const label = nodeLabelPosition(node, position, radius, layout);
            return (
              <g className={`network-node network-node-${node.kind}`} key={node.id}>
                <title>{nodeTitle(node)}</title>
                <circle
                  cx={position.x}
                  cy={position.y}
                  fill={nodeFill(node)}
                  r={radius}
                />
                <text
                  className="network-node-label"
                  textAnchor={label.anchor}
                  x={label.x}
                  y={label.y}
                >
                  {visibleNodeLabel(node)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="signal-network-legend">
        {familyNodes.map((node) => (
          <span key={node.id}>
            <i style={{ background: nodeFill(node) }} />
            {node.label}
          </span>
        ))}
      </div>
    </section>
  );
}

function MissingAnalysisState() {
  return (
    <section className="empty-state">
      <strong>Feature analysis has not been published yet</strong>
      <p>
        Generate it with <code>scripts/evaluate_model.py --feature-analysis --publish-web</code>.
        The page will show charts and CSV links after
        <code> web/public/feature-analysis/manifest.json</code> exists.
      </p>
    </section>
  );
}

function TopFeatureTable({
  rows,
  valueLabel,
}: {
  rows: TopFeature[];
  valueLabel: string;
}) {
  if (rows.length === 0) {
    return <div className="empty-state">No top feature rows were published.</div>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th>{valueLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 20).map((row) => (
            <tr key={row.feature}>
              <td>{row.feature}</td>
              <td className="score">{row.value.toFixed(5)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isManifest(value: unknown): value is AnalysisManifest {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    typeof value.generated_at === "string" &&
    Array.isArray(value.sections) &&
    isRecord(value.top_features)
  );
}

function isSignalNetwork(value: unknown): value is FeatureSignalNetwork {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    typeof value.title === "string" &&
    Array.isArray(value.nodes) &&
    Array.isArray(value.edges)
  );
}

function isImportanceAgreement(value: unknown): value is ImportanceAgreement {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    typeof value.title === "string" &&
    Array.isArray(value.methods) &&
    Array.isArray(value.rows)
  );
}

function isFeatureFamilySummary(value: unknown): value is FeatureFamilySummary {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    typeof value.title === "string" &&
    Array.isArray(value.methods) &&
    Array.isArray(value.families)
  );
}

function isGameExplanations(value: unknown): value is GameExplanations {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    typeof value.title === "string" &&
    Array.isArray(value.games)
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function buildNetworkLayout(network: FeatureSignalNetwork): {
  width: number;
  height: number;
  positions: Map<string, { x: number; y: number }>;
} {
  const width = 1040;
  const height = 620;
  const center = { x: width / 2, y: height / 2 };
  const positions = new Map<string, { x: number; y: number }>();
  positions.set("model_signal", center);

  const families = network.nodes.filter((node) => node.kind === "family");
  const featureNodes = network.nodes.filter((node) => node.kind === "feature");
  const familyRadius = 178;

  families.forEach((family, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / families.length;
    const familyPosition = {
      x: center.x + Math.cos(angle) * familyRadius,
      y: center.y + Math.sin(angle) * familyRadius,
    };
    positions.set(family.id, familyPosition);

    const members = featureNodes
      .filter((node) => node.family === family.family)
      .sort((a, b) => b.score - a.score || a.label.localeCompare(b.label));
    const tangent = { x: -Math.sin(angle), y: Math.cos(angle) };
    const outward = { x: Math.cos(angle), y: Math.sin(angle) };
    const spread = Math.min(64, 380 / Math.max(members.length, 1));
    members.forEach((feature, featureIndex) => {
      const offset = featureIndex - (members.length - 1) / 2;
      const x = familyPosition.x + outward.x * 124 + tangent.x * offset * spread;
      const y = familyPosition.y + outward.y * 104 + tangent.y * offset * spread;
      positions.set(feature.id, {
        x: clamp(x, 86, width - 86),
        y: clamp(y, 48, height - 48),
      });
    });
  });

  return { width, height, positions };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function nodeRadius(node: SignalNetworkNode): number {
  if (node.kind === "model") {
    return 34;
  }
  if (node.kind === "family") {
    return 21 + node.score * 9;
  }
  return 8 + node.score * 8;
}

function nodeFill(node: SignalNetworkNode): string {
  if (node.kind === "model") {
    return "#151716";
  }
  return node.color ?? familyColor(node.family);
}

function familyColor(family: string | undefined): string {
  const colors: Record<string, string> = {
    starter: "#2e607d",
    lineup: "#0d7a5f",
    bullpen: "#6d4c8d",
    recent_form: "#b57a16",
    team_context: "#a33b32",
    schedule: "#65716b",
    other: "#151716",
  };
  return family ? colors[family] ?? colors.other : colors.other;
}

function edgeStrokeWidth(edge: SignalNetworkEdge): number {
  if (edge.kind === "family_signal") {
    return 1.6 + edge.weight * 3.8;
  }
  if (edge.kind === "home_away_relation") {
    return 1.1;
  }
  return 0.8 + edge.weight * 2.4;
}

function labelAnchor(x: number, width: number): "start" | "middle" | "end" {
  if (x < width * 0.35) {
    return "start";
  }
  if (x > width * 0.65) {
    return "end";
  }
  return "middle";
}

function labelX(x: number, radius: number, width: number): number {
  const anchor = labelAnchor(x, width);
  if (anchor === "start") {
    return x + radius + 8;
  }
  if (anchor === "end") {
    return x - radius - 8;
  }
  return x;
}

function nodeLabelPosition(
  node: SignalNetworkNode,
  position: { x: number; y: number },
  radius: number,
  layout: { width: number; height: number },
): { x: number; y: number; anchor: "start" | "middle" | "end" } {
  if (node.kind === "model") {
    return { x: position.x, y: position.y + 4, anchor: "middle" };
  }
  if (node.kind === "family") {
    const center = { x: layout.width / 2, y: layout.height / 2 };
    const dx = position.x - center.x;
    const dy = position.y - center.y;
    const distance = Math.hypot(dx, dy) || 1;
    const x = position.x - (dx / distance) * (radius + 18);
    const y = position.y - (dy / distance) * (radius + 18) + 4;
    return { x, y, anchor: labelAnchor(x, layout.width) };
  }
  return {
    x: labelX(position.x, radius, layout.width),
    y: position.y + 4,
    anchor: labelAnchor(position.x, layout.width),
  };
}

function visibleNodeLabel(node: SignalNetworkNode): string {
  if (node.kind !== "feature") {
    return node.label;
  }
  const familyWords = ["starter", "lineup", "bullpen"];
  const label = node.label
    .split(" ")
    .filter((part) => !familyWords.includes(part))
    .join(" ")
    .replace(/\bprev\b/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return label.length > 22 ? `${label.slice(0, 19)}...` : label;
}

function nodeTitle(node: SignalNetworkNode): string {
  if (node.kind !== "feature") {
    return node.label;
  }
  const metricText = Object.entries(node.metrics ?? {})
    .map(([metric, value]) => `${metric} #${value.rank}`)
    .join(", ");
  return `${node.feature ?? node.label} | ${node.family_label ?? "Signal"} | ${metricText}`;
}

function formatFeatureSide(value: string): string {
  const labels: Record<string, string> = {
    home: "Home-side signal",
    away: "Away-side signal",
    comparison: "Home-away comparison",
    neutral: "Neutral signal",
  };
  return labels[value] ?? "Model signal";
}

function formatMethodLabel(value: string): string {
  const labels: Record<string, string> = {
    gain: "Gain",
    split: "Split",
    shap: "SHAP",
    permutation: "Permutation",
  };
  return labels[value] ?? value;
}

function compactFamilyFeatureLabel(value: string): string {
  const label = value
    .replace(/\bprev\b/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return label.length > 28 ? `${label.slice(0, 25)}...` : label;
}

function formatProbability(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatActualResult(value: number | null): string {
  if (value === null) {
    return "Result unavailable";
  }
  return value === 1 ? "Home won" : "Away won";
}

function formatContribution(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)}`;
}

function formatTimestamp(value: string): { date: string; time: string } {
  const date = new Date(value);
  return {
    date: new Intl.DateTimeFormat("en-US", {
      month: "numeric",
      day: "numeric",
      timeZone: "Asia/Seoul",
    }).format(date),
    time: new Intl.DateTimeFormat("ko-KR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Seoul",
    }).format(date),
  };
}

function formatYears(years?: number[]): string {
  return years && years.length > 0 ? years.join(", ") : "training years";
}

function formatWindow(window?: AnalysisManifest["analysis_window"]): string {
  if (!window) {
    return "analysis rows";
  }
  if (window.start_date) {
    return `${window.type} from ${window.start_date}`;
  }
  return window.type;
}

function formatDownloadLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
