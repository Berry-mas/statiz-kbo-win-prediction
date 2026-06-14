import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { ManualSubmitPanel } from "./manual-submit-panel";

type TeamInfo = {
  name: string;
  logo_key: string;
};

type PublicResult = {
  s_no: number;
  game_date: string;
  game_time?: string | null;
  home_team: TeamInfo;
  away_team: TeamInfo;
  home_score: number;
  away_score: number;
  home_win_probability: number;
  predicted_winner: "home" | "away";
  actual_winner: "home" | "away";
  correct: boolean;
  model_version: string;
  submitted_at: string;
  submission_source?: string;
};

type SchedulerSummary = {
  checked_at: string | null;
  status: string;
  reason: string | null;
  would_submit: boolean | null;
  execute_submit: boolean | null;
  starter_confirmed: boolean | null;
  batting_lineup_missing: boolean | null;
  starting_pitcher_count: number | null;
  starting_batter_count: number | null;
  home_sp_name?: string | null;
  away_sp_name?: string | null;
};

type RecentGame = {
  s_no: number | null;
  game_date: string | null;
  game_time: string | null;
  home_team: TeamInfo;
  away_team: TeamInfo;
  home_sp_name?: string | null;
  away_sp_name?: string | null;
  game_status: "scheduled" | "in_progress" | "final" | "cancelled";
  submitted_at: string;
  submission_source: string;
  model_version: string;
  probability_published: boolean;
  home_win_probability: number | null;
  predicted_winner: "home" | "away" | null;
  home_score: number | null;
  away_score: number | null;
  actual_winner: "home" | "away" | null;
  correct: boolean | null;
  scheduler: SchedulerSummary | null;
};

type SubmissionBatch = {
  game_date: string;
  source: string;
  submitted_at: string;
  submitted_games: number;
  model_version: string;
  games: Array<{
    s_no: number | null;
    home_team: TeamInfo;
    away_team: TeamInfo;
    game_status: string;
  }>;
};

type ManualWorkflow = {
  name: string;
  status: "success" | "failed" | "unknown";
  last_checked_at: string | null;
  last_game_date: string | null;
  submitted_games: number;
  source: string;
  note?: string;
};

type ModelMetrics = {
  window: {
    type: string;
    requested: number;
    sample_size: number;
  };
  accuracy: number | null;
  log_loss: number | null;
  brier: number | null;
};

type DashboardData = {
  schema_version?: number;
  generated_at: string;
  model_version?: string | null;
  manual_workflow?: ManualWorkflow;
  latest_submission?: SubmissionBatch | null;
  recent_submissions?: SubmissionBatch[];
  recent_games?: RecentGame[];
  model_metrics?: ModelMetrics;
  results: PublicResult[];
};

type Metric = {
  label: string;
  value: string;
  detail: string;
  tone?: "good" | "warn" | "neutral";
};

const DATA_FILE = path.join(process.cwd(), "public", "results.json");
const PUBLIC_DIR = path.join(process.cwd(), "public");
const EPSILON = 1e-15;
const LG_TWINS_LOGO_KEY = "lg";

export const dynamic = "force-static";

export default async function DashboardPage() {
  const data = normalizeDashboardData(await loadDashboardData());
  const results = sortResults(data.results);
  const recentGames = data.recent_games ?? [];
  const ledgerGames = recentGames.filter((game) => game.game_status === "final" || game.game_status === "cancelled");
  const metrics = data.model_metrics ?? buildModelMetrics(results, 20);
  const metricCards = buildMetricCards(results, recentGames, metrics);
  const latestSubmission = data.latest_submission ?? null;
  const modelVersion = data.model_version ?? results[0]?.model_version ?? "n/a";
  const heroGame = recentGames.find(isLgTwinsGame) ?? null;

  return (
    <main className="dashboard-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Y-wins KBO Forecast</p>
          <h1>Y-wins KBO Prediction</h1>
          <div className="model-line" aria-label="Model version">
            <span>model</span>
            <strong>{modelVersion}</strong>
          </div>
        </div>
        <div className="hero-board">
          {heroGame ? (
            <GameCard game={heroGame} featured />
          ) : (
            <div className="hero-empty">
              <strong>No LG Twins game yet</strong>
              <span>Waiting for the latest submitted LG Twins matchup</span>
            </div>
          )}
        </div>
      </section>

      <section className="metric-grid" aria-label="Model operating metrics">
        {metricCards.map((metric) => (
          <article className={`metric-card tone-${metric.tone ?? "neutral"}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p>{metric.detail}</p>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <section className="main-column">
          <article className="section-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Submitted games</p>
              </div>
              <span className="policy-chip">
                {metrics.window.sample_size}/{metrics.window.requested} metric window
              </span>
            </div>
            {recentGames.length > 0 ? (
              <div className="game-grid">
                {recentGames.map((game) => (
                  <GameCard game={game} key={`${game.s_no}-${game.submitted_at}`} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="Published games will appear here"
                body="Submitted games show submitted probability; outcomes appear after final score."
              />
            )}
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Finalized ledger</p>
                <h2>확정 결과</h2>
              </div>
            </div>
            {ledgerGames.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Matchup</th>
                      <th>Final</th>
                      <th>Home Win</th>
                      <th>Call</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledgerGames.map((game) => {
                      return (
                        <tr key={game.s_no}>
                          <td>{formatDate(game.game_date ?? game.submitted_at)}</td>
                          <td>
                            <span className="matchup">
                              {game.away_team.name} <span>vs</span> {game.home_team.name}
                            </span>
                            <span className="venue">{game.submission_source ?? "auto"}</span>
                          </td>
                          <td className="score">
                            {game.game_status === "cancelled" || game.away_score === null || game.home_score === null
                              ? "Cancelled"
                              : `${game.away_score}-${game.home_score}`}
                          </td>
                          <td>
                            {game.home_win_probability !== null ? (
                              <ProbabilityBar value={game.home_win_probability / 100} />
                            ) : (
                              "n/a"
                            )}
                          </td>
                          <td>
                            {game.predicted_winner === "home"
                              ? game.home_team.name
                              : game.predicted_winner === "away"
                                ? game.away_team.name
                                : "n/a"}
                          </td>
                          <td>
                            <OutcomeBadge correct={game.correct} status={game.game_status} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No finalized submissions published yet"
                body="Rows are published after a submitted game has a final score."
              />
            )}
          </article>
        </section>

        <aside className="side-column">
          <article className="section-panel operations-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Manual workflow</p>
              </div>
              <StatusPill status={data.manual_workflow?.status ?? "unknown"} />
            </div>
            <ManualSubmitPanel />
            <WorkflowSummary workflow={data.manual_workflow} />
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Latest submission</p>
              </div>
            </div>
            {latestSubmission ? (
              <SubmissionSummary batch={latestSubmission} />
            ) : (
              <EmptyState title="No batch" body="No successful submission batch has been published." />
            )}
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow">Model ops</p>
              </div>
            </div>
            <dl className="ops-list">
              <div>
                <dt>Accuracy</dt>
                <dd>{formatRate(metrics.accuracy)}</dd>
              </div>
              <div>
                <dt>LogLoss</dt>
                <dd>{formatNumber(metrics.log_loss)}</dd>
              </div>
              <div>
                <dt>Brier</dt>
                <dd>{formatNumber(metrics.brier)}</dd>
              </div>
              <div>
                <dt>Window</dt>
                <dd>{metrics.window.sample_size} games</dd>
              </div>
            </dl>
          </article>
        </aside>
      </section>
    </main>
  );
}

async function loadDashboardData(): Promise<DashboardData> {
  const file = await readFile(DATA_FILE, "utf8");
  const parsed = JSON.parse(file) as unknown;

  if (!isDashboardData(parsed)) {
    throw new Error("Invalid public result dashboard data.");
  }

  return parsed;
}

function normalizeDashboardData(data: DashboardData): DashboardData {
  return {
    ...data,
    results: sortResults(data.results),
    recent_games: data.recent_games ?? [],
    model_metrics: data.model_metrics ?? buildModelMetrics(data.results, 20),
  };
}

function isDashboardData(value: unknown): value is DashboardData {
  return isRecord(value) && typeof value.generated_at === "string" && Array.isArray(value.results);
}

function sortResults(results: PublicResult[]): PublicResult[] {
  return [...results].sort((a, b) => {
    const dateOrder = b.game_date.localeCompare(a.game_date);
    return dateOrder !== 0 ? dateOrder : b.s_no - a.s_no;
  });
}

function buildMetricCards(results: PublicResult[], recentGames: RecentGame[], metrics: ModelMetrics): Metric[] {
  const latestGame = recentGames[0];
  const openSubmitted = recentGames.filter((game) => game.game_status === "scheduled" || game.game_status === "in_progress").length;
  const latestDate = latestGame ? formatDate(latestGame.game_date ?? latestGame.submitted_at) : "n/a";
  const latestDetail = latestGame ? "Submission date" : "No submitted game";

  return [
    {
      label: "Last submit",
      value: latestDate,
      detail: latestDetail,
      tone: "neutral",
    },
    {
      label: "Accuracy",
      value: formatRate(metrics.accuracy),
      detail: `${metrics.window.sample_size} finalized games`,
      tone: "good",
    },
    {
      label: "LogLoss",
      value: formatNumber(metrics.log_loss),
      detail: "Recent finalized submissions",
      tone: "neutral",
    },
    {
      label: "Open submitted",
      value: String(openSubmitted),
      detail: `${results.length} finalized public rows`,
      tone: openSubmitted > 0 ? "warn" : "neutral",
    },
  ];
}

function buildModelMetrics(results: PublicResult[], requested: number): ModelMetrics {
  const window = sortResults(results).slice(0, requested);
  if (window.length === 0) {
    return {
      window: { type: "recent_finalized_submitted_games", requested, sample_size: 0 },
      accuracy: null,
      log_loss: null,
      brier: null,
    };
  }

  const correct = window.filter((game) => game.correct).length;
  const logLoss = average(
    window.map((game) => {
      const outcome = game.actual_winner === "home" ? 1 : 0;
      const probability = clampProbability(game.home_win_probability / 100);
      return -(outcome * Math.log(probability) + (1 - outcome) * Math.log(1 - probability));
    }),
  );
  const brier = average(
    window.map((game) => {
      const outcome = game.actual_winner === "home" ? 1 : 0;
      return (game.home_win_probability / 100 - outcome) ** 2;
    }),
  );

  return {
    window: { type: "recent_finalized_submitted_games", requested, sample_size: window.length },
    accuracy: correct / window.length,
    log_loss: logLoss,
    brier,
  };
}

function average(values: number[]): number {
  if (values.length === 0) {
    return Number.NaN;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function clampProbability(value: number): number {
  return Math.min(Math.max(value, EPSILON), 1 - EPSILON);
}

function isLgTwinsGame(game: RecentGame): boolean {
  return game.home_team.logo_key === LG_TWINS_LOGO_KEY || game.away_team.logo_key === LG_TWINS_LOGO_KEY;
}

function GameCard({ game, featured = false }: { game: RecentGame; featured?: boolean }) {
  const homeTeam = game.home_team;
  const awayTeam = game.away_team;
  const homeProbability =
    game.probability_published && game.home_win_probability !== null ? game.home_win_probability : null;
  const awayProbability = homeProbability !== null ? 100 - homeProbability : null;
  const predictedTeam =
    game.predicted_winner === "home" ? homeTeam : game.predicted_winner === "away" ? awayTeam : null;
  const awayPitcher = (game.away_sp_name ?? game.scheduler?.away_sp_name)?.trim();
  const homePitcher = (game.home_sp_name ?? game.scheduler?.home_sp_name)?.trim();

  return (
    <article className={`game-card ${featured ? "game-card-featured" : ""}`}>
      <div className="game-card-top">
        <span>{formatDate(game.game_date ?? game.submitted_at)}</span>
        <StatusPill status={game.game_status} />
      </div>
      <div className="teams">
        <div className="team-side team-side-away">
          <span>Away</span>
          <TeamLogo team={awayTeam} />
        </div>
        {awayProbability !== null ? (
          <div className="team-probability team-probability-away">
            <strong>{formatProbabilityLabel(awayProbability)}</strong>
            {awayPitcher ? <span className="pitcher-matchup">{awayPitcher}</span> : null}
          </div>
        ) : (
          <div className="team-probability-placeholder" />
        )}
        <div className="versus">
          <div className="team-matchup">
            <strong>{awayTeam.name}</strong>
            <span>vs</span>
            <strong>{homeTeam.name}</strong>
          </div>
        </div>
        {homeProbability !== null ? (
          <div className="team-probability team-probability-home">
            <strong>{formatProbabilityLabel(homeProbability)}</strong>
            {homePitcher ? <span className="pitcher-matchup">{homePitcher}</span> : null}
          </div>
        ) : (
          <div className="team-probability-placeholder" />
        )}
        <div className="team-side team-side-home">
          <span>Home</span>
          <TeamLogo team={homeTeam} />
        </div>
      </div>
      <div className="game-card-bottom">
        <div className="probability-panel">
          {game.probability_published && game.home_win_probability !== null ? (
            <MatchupProbabilityBar homeValue={game.home_win_probability / 100} homeTeam={homeTeam} awayTeam={awayTeam} />
          ) : (
            <div className="submission-seal">
              <strong>Submitted</strong>
              <span>Sealed</span>
            </div>
          )}
        </div>
      </div>
      <div className="game-footer">
        <span>
          {game.model_version} · Submitted {formatTimestamp(game.submitted_at)}
        </span>
        {game.game_status === "final" && game.away_score !== null && game.home_score !== null ? (
          <strong>
            {game.away_score}-{game.home_score} · {game.correct ? "Hit" : "Miss"}
          </strong>
        ) : (
          <strong>{predictedTeam ? predictedTeam.name : "Pending result"}</strong>
        )}
      </div>
      {game.scheduler ? (
        <div className="scheduler-line">
          <span>{statusLabel(game.scheduler.status)}</span>
          <span>
            lineup {game.scheduler.batting_lineup_missing ? "fallback" : "ready"}
          </span>
        </div>
      ) : null}
    </article>
  );
}

function TeamLogo({ team }: { team: TeamInfo }) {
  const src = logoSrc(team.logo_key);
  return (
    <div className="team-logo" aria-label={`${team.name} logo`}>
      {src ? <img alt="" src={src} /> : <span>{teamInitials(team.name)}</span>}
    </div>
  );
}

function logoSrc(logoKey: string): string | null {
  for (const ext of ["svg", "png", "webp"]) {
    const candidate = path.join(PUBLIC_DIR, "team-logos", `${logoKey}.${ext}`);
    if (existsSync(candidate)) {
      return `/team-logos/${logoKey}.${ext}`;
    }
  }
  return null;
}

function ProbabilityBar({ value }: { value: number }) {
  const percentage = Math.round(value * 100);
  return (
    <div className="probability" aria-label={`${percentage} percent home win probability`}>
      <span>{percentage}%</span>
      <div>
        <i style={{ width: `${percentage}%` }} />
      </div>
    </div>
  );
}

function MatchupProbabilityBar({
  homeValue,
  homeTeam,
  awayTeam,
}: {
  homeValue: number;
  homeTeam: TeamInfo;
  awayTeam: TeamInfo;
}) {
  const homePercentage = clampProbability(homeValue) * 100;
  const awayPercentage = 100 - homePercentage;
  const homeLabel = formatProbabilityLabel(homePercentage);
  const awayLabel = formatProbabilityLabel(awayPercentage);

  return (
    <div
      className="matchup-probability"
      aria-label={`${awayTeam.name} ${awayLabel}, ${homeTeam.name} ${homeLabel}`}
    >
      <div className="matchup-probability-bar">
        <i className="away-probability" style={{ width: `${awayPercentage}%` }} />
        <i className="home-probability" style={{ width: `${homePercentage}%` }} />
      </div>
    </div>
  );
}

function formatProbabilityLabel(value: number): string {
  return `${value.toFixed(2)}%`;
}

function OutcomeBadge({ correct, status }: { correct: boolean | null; status?: RecentGame["game_status"] }) {
  if (status === "cancelled") {
    return <span className="badge badge-neutral">Cancelled</span>;
  }
  if (correct === null) {
    return <span className="badge badge-neutral">Pending</span>;
  }
  return <span className={`badge ${correct ? "badge-good" : "badge-bad"}`}>{correct ? "Hit" : "Miss"}</span>;
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{statusLabel(status)}</span>;
}

function WorkflowSummary({ workflow }: { workflow?: ManualWorkflow }) {
  const row = workflow ?? {
    name: "Manual Statiz submit",
    status: "unknown" as const,
    last_checked_at: null,
    last_game_date: null,
    submitted_games: 0,
    source: "submission_log",
  };

  return (
    <dl className="ops-list">
      <div>
        <dt>Last run</dt>
        <dd>{row.last_checked_at ? formatTimestamp(row.last_checked_at) : "unknown"}</dd>
      </div>
      <div>
        <dt>Game date</dt>
        <dd>{row.last_game_date ?? "unknown"}</dd>
      </div>
      <div>
        <dt>Submitted</dt>
        <dd>{row.submitted_games}</dd>
      </div>
    </dl>
  );
}

function SubmissionSummary({ batch }: { batch: SubmissionBatch }) {
  return (
    <div className="submission-summary">
      <strong>{batch.submitted_games} games</strong>
      <span>
        {batch.source} · {formatTimestamp(batch.submitted_at)}
      </span>
      <div className="mini-matchups">
        {batch.games.slice(0, 5).map((game) => (
          <span key={`${game.s_no}-${game.home_team.logo_key}`}>
            {game.away_team.name} vs {game.home_team.name}
          </span>
        ))}
      </div>
    </div>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function teamInitials(name: string): string {
  if (/^[A-Za-z]+$/.test(name)) {
    return name.slice(0, 3).toUpperCase();
  }
  return name.slice(0, 2);
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    success: "성공",
    failed: "실패",
    unknown: "미확인",
    final: "Final",
    scheduled: "Scheduled",
    in_progress: "Live",
    cancelled: "Cancelled",
    ready: "준비 완료",
    lineup_missing_fallback: "라인업 대기",
    already_submitted: "제출 완료",
    too_early: "대기 중",
    past_safe_cutoff: "안전 마감",
    past_hard_deadline: "제출 마감",
  };
  return labels[status] ?? status;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  }).format(new Date(value));
}

function formatRate(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "n/a" : `${Math.round(value * 100)}%`;
}

function formatNumber(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "n/a" : value.toFixed(3);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
