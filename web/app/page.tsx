import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";

import { DatePager } from "./date-pager";
import { ManualSubmitPanel } from "./manual-submit-panel";
import { SiteStatsStrip } from "./site-stats";

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
  labelKo: string;
  value: string;
  detail: string;
  detailKo: string;
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
  const recentGamePages = groupGamesBySubmittedDate(recentGames).map(({ key, games }) => ({
    key,
    label: formatDate(key),
    detail: `${formatGameCount(games.length)} submitted`,
    detailKo: `${formatGameCountKo(games.length)} 제출`,
    content: (
      <div className="game-grid">
        {games.map((game) => (
          <GameCard game={game} key={`${game.s_no ?? "unknown"}-${game.submitted_at}`} />
        ))}
      </div>
    ),
  }));
  const ledgerPages = groupGamesByDate(ledgerGames).map(({ key, games }) => ({
    key,
    label: formatDate(key),
    detail: formatGameCount(games.length),
    detailKo: formatGameCountKo(games.length),
    content: <LedgerTable games={games} />,
  }));

  return (
    <main className="dashboard-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Y-wins KBO Forecast</p>
          <h1 data-en="KBO win probability dashboard" data-ko="KBO 승부예측 대시보드">
            KBO win probability dashboard
          </h1>
          <div className="model-line" aria-label="Model version">
            <span data-en="model" data-ko="모델">
              model
            </span>
            <strong>{modelVersion}</strong>
          </div>
        </div>
        <div className="hero-board">
          {heroGame ? (
            <GameCard game={heroGame} featured />
          ) : (
            <div className="hero-empty">
              <strong data-en="No LG Twins game yet" data-ko="아직 LG 트윈스 경기가 없음">
                No LG Twins game yet
              </strong>
              <span
                data-en="Waiting for the latest submitted LG Twins matchup"
                data-ko="최근 제출된 LG 트윈스 경기를 기다리는 중"
              >
                Waiting for the latest submitted LG Twins matchup
              </span>
            </div>
          )}
        </div>
      </section>

      <SiteStatsStrip />

      <section className="metric-grid" aria-label="Model operating metrics">
        {metricCards.map((metric) => (
          <article className={`metric-card tone-${metric.tone ?? "neutral"}`} key={metric.label}>
            <span data-en={metric.label} data-ko={metric.labelKo}>
              {metric.label}
            </span>
            <strong>{metric.value}</strong>
            <p data-en={metric.detail} data-ko={metric.detailKo}>
              {metric.detail}
            </p>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <section className="main-column">
          <article className="section-panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow" data-en="Submitted games" data-ko="제출 경기">
                  Submitted games
                </p>
              </div>
              <span className="policy-chip">
                {metrics.window.sample_size}/{metrics.window.requested}{" "}
                <span data-en="metric window" data-ko="지표 구간">
                  metric window
                </span>
              </span>
            </div>
            {recentGames.length > 0 ? (
              <DatePager ariaLabel="Submitted games by date" pages={recentGamePages} />
            ) : (
              <EmptyState
                title="Published games will appear here"
                titleKo="게시된 경기가 여기에 표시됨"
                body="Submitted games show submitted probability; outcomes appear after final score."
                bodyKo="제출된 경기는 제출 확률을 보여주고, 최종 점수 이후 결과가 표시됨."
              />
            )}
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow" data-en="Finalized ledger" data-ko="확정 결과 기록">
                  Finalized ledger
                </p>
              </div>
            </div>
            {ledgerGames.length > 0 ? (
              <DatePager ariaLabel="Finalized ledger by date" pages={ledgerPages} />
            ) : (
              <EmptyState
                title="No finalized submissions published yet"
                titleKo="아직 확정된 제출 결과가 없음"
                body="Rows are published after a submitted game has a final score."
                bodyKo="제출된 경기가 최종 점수를 갖게 되면 행이 게시됨."
              />
            )}
          </article>
        </section>

        <aside className="side-column">
          <article className="section-panel operations-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow" data-en="Manual workflow" data-ko="수동 제출">
                  Manual workflow
                </p>
              </div>
              <StatusPill status={data.manual_workflow?.status ?? "unknown"} />
            </div>
            <ManualSubmitPanel />
            <WorkflowSummary workflow={data.manual_workflow} />
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow" data-en="Latest submission" data-ko="최근 제출">
                  Latest submission
                </p>
              </div>
            </div>
            {latestSubmission ? (
              <SubmissionSummary batch={latestSubmission} />
            ) : (
              <EmptyState
                title="No batch"
                titleKo="제출 묶음 없음"
                body="No successful submission batch has been published."
                bodyKo="게시된 성공 제출 묶음이 없음."
              />
            )}
          </article>

          <article className="section-panel">
            <div className="section-heading compact">
              <div>
                <p className="eyebrow" data-en="Model ops" data-ko="모델 운영">
                  Model ops
                </p>
              </div>
            </div>
            <dl className="ops-list">
              <div>
                <dt data-en="Accuracy" data-ko="정확도">Accuracy</dt>
                <dd>{formatRate(metrics.accuracy)}</dd>
              </div>
              <div>
                <dt data-en="LogLoss" data-ko="로그손실">LogLoss</dt>
                <dd>{formatNumber(metrics.log_loss)}</dd>
              </div>
              <div>
                <dt data-en="Brier" data-ko="브라이어">Brier</dt>
                <dd>{formatNumber(metrics.brier)}</dd>
              </div>
              <div>
                <dt data-en="Window" data-ko="구간">Window</dt>
                <dd>
                  {metrics.window.sample_size}{" "}
                  <span data-en="games" data-ko="경기">
                    games
                  </span>
                </dd>
              </div>
            </dl>
            <div className="ops-links">
              <a
                className="quiet-link"
                data-en="Feature analysis"
                data-ko="Feature 분석"
                href="/feature-analysis"
              >
                Feature analysis
              </a>
              <a
                className="quiet-link"
                data-en="Model & feature guide"
                data-ko="모델/변수 설명"
                href="/model-guide"
              >
                Model & feature guide
              </a>
            </div>
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
  const latestDate = latestGame ? formatDate(latestGame.submitted_at) : "n/a";
  const latestDetail = latestGame ? "Submission date" : "No submitted game";
  const latestDetailKo = latestGame ? "제출일 기준" : "제출된 경기 없음";

  return [
    {
      label: "Last submit",
      labelKo: "최근 제출",
      value: latestDate,
      detail: latestDetail,
      detailKo: latestDetailKo,
      tone: "neutral",
    },
    {
      label: "Accuracy",
      labelKo: "정확도",
      value: formatRate(metrics.accuracy),
      detail: `${metrics.window.sample_size} finalized games`,
      detailKo: `확정 경기 ${metrics.window.sample_size}개`,
      tone: "good",
    },
    {
      label: "LogLoss",
      labelKo: "로그손실",
      value: formatNumber(metrics.log_loss),
      detail: "Recent finalized submissions",
      detailKo: "최근 확정 제출 기준",
      tone: "neutral",
    },
    {
      label: "Open submitted",
      labelKo: "미확정 제출",
      value: String(openSubmitted),
      detail: `${results.length} finalized public rows`,
      detailKo: `공개 확정 행 ${results.length}개`,
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

function groupGamesByDate(games: RecentGame[]): Array<{ key: string; games: RecentGame[] }> {
  return groupGamesByKey(games, gameDateKey);
}

function groupGamesBySubmittedDate(games: RecentGame[]): Array<{ key: string; games: RecentGame[] }> {
  return groupGamesByKey(games, submittedDateKey);
}

function groupGamesByKey(
  games: RecentGame[],
  keyForGame: (game: RecentGame) => string,
): Array<{ key: string; games: RecentGame[] }> {
  const groups = new Map<string, RecentGame[]>();
  for (const game of games) {
    const key = keyForGame(game);
    const group = groups.get(key);
    if (group) {
      group.push(game);
    } else {
      groups.set(key, [game]);
    }
  }
  return Array.from(groups, ([key, group]) => ({ key, games: group })).sort((a, b) =>
    a.key.localeCompare(b.key),
  );
}

function gameDateKey(game: RecentGame): string {
  if (game.game_date) {
    return game.game_date;
  }
  return game.submitted_at.slice(0, 10);
}

function submittedDateKey(game: RecentGame): string {
  return game.submitted_at.slice(0, 10);
}

function LedgerTable({ games }: { games: RecentGame[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th data-en="Date" data-ko="날짜">Date</th>
            <th data-en="Matchup" data-ko="매치업">Matchup</th>
            <th data-en="Final" data-ko="최종">Final</th>
            <th data-en="Home Win" data-ko="홈 승률">Home Win</th>
            <th data-en="Call" data-ko="예측">Call</th>
            <th data-en="Result" data-ko="결과">Result</th>
          </tr>
        </thead>
        <tbody>
          {games.map((game) => {
            return (
              <tr key={`${game.s_no ?? "unknown"}-${game.submitted_at}`}>
                <td>{formatDate(game.game_date ?? game.submitted_at)}</td>
                <td>
                  <span className="matchup">
                    {game.away_team.name} <span>vs</span> {game.home_team.name}
                  </span>
                  <span className="venue">{game.submission_source ?? "auto"}</span>
                </td>
                <td className="score">
                  {game.game_status === "cancelled" || game.away_score === null || game.home_score === null ? (
                    <span data-en="Cancelled" data-ko="취소">Cancelled</span>
                  ) : (
                    `${game.away_score}-${game.home_score}`
                  )}
                </td>
                <td>
                  {game.home_win_probability !== null ? <ProbabilityBar value={game.home_win_probability / 100} /> : "n/a"}
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
  );
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
  const schedulerStatus = game.scheduler ? statusLabels(game.scheduler.status) : null;
  const lineupLabel = game.scheduler?.batting_lineup_missing
    ? { en: "lineup fallback", ko: "라인업 대기" }
    : { en: "lineup ready", ko: "라인업 준비" };

  return (
    <article className={`game-card ${featured ? "game-card-featured" : ""}`}>
      <div className="game-card-top">
        <span>{formatDate(game.game_date ?? game.submitted_at)}</span>
        <StatusPill status={game.game_status} />
      </div>
      <div className="teams">
        <div className="team-side team-side-away">
          <span data-en="Away" data-ko="원정">Away</span>
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
          <span data-en="Home" data-ko="홈">Home</span>
          <TeamLogo team={homeTeam} />
        </div>
      </div>
      <div className="game-card-bottom">
        <div className="probability-panel">
          {game.probability_published && game.home_win_probability !== null ? (
            <MatchupProbabilityBar homeValue={game.home_win_probability / 100} homeTeam={homeTeam} awayTeam={awayTeam} />
          ) : (
            <div className="submission-seal">
              <strong data-en="Submitted" data-ko="제출 완료">Submitted</strong>
              <span data-en="Sealed" data-ko="비공개">Sealed</span>
            </div>
          )}
        </div>
      </div>
      <div className="game-footer">
        <span>
          {game.model_version} ·{" "}
          <span data-en="Submitted" data-ko="제출">
            Submitted
          </span>{" "}
          {formatTimestamp(game.submitted_at)}
        </span>
        {game.game_status === "final" && game.away_score !== null && game.home_score !== null ? (
          <strong>
            {game.away_score}-{game.home_score} ·{" "}
            <span data-en={game.correct ? "Hit" : "Miss"} data-ko={game.correct ? "적중" : "오답"}>
              {game.correct ? "Hit" : "Miss"}
            </span>
          </strong>
        ) : game.game_status === "cancelled" ? (
          <strong data-en="Cancelled" data-ko="취소">Cancelled</strong>
        ) : (
          <strong>
            {predictedTeam ? (
              predictedTeam.name
            ) : (
              <span data-en="Pending result" data-ko="결과 대기">
                Pending result
              </span>
            )}
          </strong>
        )}
      </div>
      {game.scheduler ? (
        <div className="scheduler-line">
          <span data-en={schedulerStatus?.en} data-ko={schedulerStatus?.ko}>
            {schedulerStatus?.en}
          </span>
          <span data-en={lineupLabel.en} data-ko={lineupLabel.ko}>
            {lineupLabel.en}
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
    return (
      <span className="badge badge-neutral" data-en="Cancelled" data-ko="취소">
        Cancelled
      </span>
    );
  }
  if (correct === null) {
    return (
      <span className="badge badge-neutral" data-en="Pending" data-ko="대기">
        Pending
      </span>
    );
  }
  return (
    <span
      className={`badge ${correct ? "badge-good" : "badge-bad"}`}
      data-en={correct ? "Hit" : "Miss"}
      data-ko={correct ? "적중" : "오답"}
    >
      {correct ? "Hit" : "Miss"}
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const labels = statusLabels(status);
  return (
    <span className={`status-pill status-${status}`} data-en={labels.en} data-ko={labels.ko}>
      {labels.en}
    </span>
  );
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
        <dt data-en="Last run" data-ko="최근 실행">Last run</dt>
        <dd>{row.last_checked_at ? formatTimestamp(row.last_checked_at) : "unknown"}</dd>
      </div>
      <div>
        <dt data-en="Game date" data-ko="경기일">Game date</dt>
        <dd>{row.last_game_date ? formatFullDate(row.last_game_date) : "unknown"}</dd>
      </div>
      <div>
        <dt data-en="Submitted" data-ko="제출 수">Submitted</dt>
        <dd>{row.submitted_games}</dd>
      </div>
    </dl>
  );
}

function SubmissionSummary({ batch }: { batch: SubmissionBatch }) {
  return (
    <div className="submission-summary">
      <strong>
        {batch.submitted_games}{" "}
        <span data-en="games" data-ko="경기">
          games
        </span>
      </strong>
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

function EmptyState({
  title,
  titleKo,
  body,
  bodyKo,
}: {
  title: string;
  titleKo: string;
  body: string;
  bodyKo: string;
}) {
  return (
    <div className="empty-state">
      <strong data-en={title} data-ko={titleKo}>
        {title}
      </strong>
      <p data-en={body} data-ko={bodyKo}>
        {body}
      </p>
    </div>
  );
}

function teamInitials(name: string): string {
  if (/^[A-Za-z]+$/.test(name)) {
    return name.slice(0, 3).toUpperCase();
  }
  return name.slice(0, 2);
}

function statusLabels(status: string): { en: string; ko: string } {
  const labels: Record<string, { en: string; ko: string }> = {
    success: { en: "Success", ko: "성공" },
    failed: { en: "Failed", ko: "실패" },
    unknown: { en: "Unknown", ko: "미확인" },
    final: { en: "Final", ko: "종료" },
    scheduled: { en: "Scheduled", ko: "예정" },
    in_progress: { en: "Live", ko: "진행 중" },
    cancelled: { en: "Cancelled", ko: "취소" },
    ready: { en: "Ready", ko: "준비 완료" },
    lineup_missing_fallback: { en: "Lineup fallback", ko: "라인업 대기" },
    already_submitted: { en: "Already submitted", ko: "제출 완료" },
    too_early: { en: "Waiting", ko: "대기 중" },
    past_safe_cutoff: { en: "Safe cutoff", ko: "안전 마감" },
    past_hard_deadline: { en: "Deadline passed", ko: "제출 마감" },
  };
  return labels[status] ?? { en: status, ko: status };
}

function formatDate(value: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    month: "numeric",
    day: "numeric",
    timeZone: "Asia/Seoul",
  }).formatToParts(new Date(value));
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  return `${month}.${day}`;
}

function formatFullDate(value: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Seoul",
  }).formatToParts(new Date(value));
  const year = parts.find((part) => part.type === "year")?.value ?? "";
  const month = parts.find((part) => part.type === "month")?.value ?? "";
  const day = parts.find((part) => part.type === "day")?.value ?? "";
  return `${year}.${month}.${day}`;
}

function formatGameCount(value: number): string {
  return `${value} ${value === 1 ? "game" : "games"}`;
}

function formatGameCountKo(value: number): string {
  return `${value}경기`;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  const dateLabel = formatDate(value);
  const timeLabel = new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Seoul",
  }).format(date);
  return `${dateLabel} ${timeLabel}`;
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
