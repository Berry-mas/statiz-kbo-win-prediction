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

      {manifest ? <AnalysisContent manifest={manifest} /> : <MissingAnalysisState />}
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

function AnalysisContent({ manifest }: { manifest: AnalysisManifest }) {
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
