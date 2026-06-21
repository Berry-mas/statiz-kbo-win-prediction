import {
  formatDateLabel,
  formatTimeLabel,
  loadPublicDashboardData,
  sortedRecentGames,
  teamLogoSrc,
  type RecentGame,
  type TeamInfo,
} from "../public-data";

type LineupState = {
  label: string;
  labelKo: string;
  detail: string;
  detailKo: string;
  tone: "good" | "warn" | "neutral";
};

export const dynamic = "force-static";

export default async function LineupPage() {
  const data = await loadPublicDashboardData();
  const games = sortedRecentGames(data);
  const starterPairs = games.filter((game) => starterName(game, "home") && starterName(game, "away"));
  const fullLineups = games.filter((game) => game.scheduler?.batting_lineup_missing === false);
  const fallbackLineups = games.filter((game) => game.scheduler?.batting_lineup_missing === true);

  return (
    <main className="dashboard-shell">
      <section className="feature-page-heading">
        <div>
          <p className="eyebrow" data-en="Lineup" data-ko="라인업">
            Lineup
          </p>
          <h1 data-en="Starter and lineup readiness" data-ko="선발/라인업 준비 상태">
            Starter and lineup readiness
          </h1>
        </div>
        <div className="page-actions">
          <a className="quiet-link" data-en="Dashboard" data-ko="대시보드" href="/">
            Dashboard
          </a>
          <a className="quiet-link" data-en="Model guide" data-ko="모델 설명" href="/model-guide">
            Model guide
          </a>
        </div>
      </section>

      <section className="metric-grid" aria-label="Lineup facts">
        <article className="metric-card">
          <span data-en="Public games" data-ko="공개 경기">
            Public games
          </span>
          <strong>{games.length}</strong>
          <p data-en="Recent submitted games in the public feed" data-ko="공개 피드의 최근 제출 경기">
            Recent submitted games in the public feed
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Starter pairs" data-ko="선발 매치업">
            Starter pairs
          </span>
          <strong>{starterPairs.length}</strong>
          <p data-en="Games with both probable starters published" data-ko="양팀 선발명이 공개된 경기">
            Games with both probable starters published
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Full lineup logs" data-ko="전체 라인업 로그">
            Full lineup logs
          </span>
          <strong>{fullLineups.length}</strong>
          <p data-en="Scheduler rows marked batting-lineup ready" data-ko="타자 라인업 준비로 기록된 스케줄러 행">
            Scheduler rows marked batting-lineup ready
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Fallback logs" data-ko="Fallback 로그">
            Fallback logs
          </span>
          <strong>{fallbackLineups.length}</strong>
          <p data-en="Rows submitted before full batting order arrived" data-ko="전체 타순 도착 전 제출된 행">
            Rows submitted before full batting order arrived
          </p>
        </article>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Recent lineup board" data-ko="최근 라인업 보드">
              Recent lineup board
            </p>
            <p
              data-en="The public export currently includes starters and scheduler readiness, not private full batting-order rows."
              data-ko="현재 공개 export에는 선발투수와 스케줄러 준비 상태만 포함되며, 비공개 전체 타순 행은 노출하지 않음."
            >
              The public export currently includes starters and scheduler readiness, not private full batting-order rows.
            </p>
          </div>
        </div>
        <div className="lineup-card-grid">
          {games.map((game) => (
            <LineupCard game={game} key={`${game.s_no ?? "unknown"}-${game.submitted_at}`} />
          ))}
        </div>
      </section>
    </main>
  );
}

function LineupCard({ game }: { game: RecentGame }) {
  const state = lineupState(game);
  return (
    <article className={`lineup-card tone-${state.tone}`}>
      <div className="lineup-card-head">
        <div>
          <strong>
            {formatDateLabel(game.game_date)} · {formatTimeLabel(game.game_time)}
          </strong>
          <span>{game.submission_source} · {game.model_version}</span>
        </div>
        <span data-en={state.label} data-ko={state.labelKo}>
          {state.label}
        </span>
      </div>
      <div className="lineup-matchup">
        <LineupTeam team={game.away_team} pitcher={starterName(game, "away")} side="Away" sideKo="원정" />
        <span>vs</span>
        <LineupTeam team={game.home_team} pitcher={starterName(game, "home")} side="Home" sideKo="홈" />
      </div>
      <dl className="detail-stat-list">
        <div>
          <dt data-en="Pitchers" data-ko="투수">
            Pitchers
          </dt>
          <dd>{formatCount(game.scheduler?.starting_pitcher_count)}</dd>
        </div>
        <div>
          <dt data-en="Batters" data-ko="타자">
            Batters
          </dt>
          <dd>{formatCount(game.scheduler?.starting_batter_count)}</dd>
        </div>
        <div>
          <dt data-en="Status" data-ko="상태">
            Status
          </dt>
          <dd>{game.scheduler?.status ?? game.game_status}</dd>
        </div>
      </dl>
      <p data-en={state.detail} data-ko={state.detailKo}>
        {state.detail}
      </p>
    </article>
  );
}

function LineupTeam({
  team,
  pitcher,
  side,
  sideKo,
}: {
  team: TeamInfo;
  pitcher: string | null;
  side: string;
  sideKo: string;
}) {
  return (
    <div className="lineup-team">
      <img alt="" src={teamLogoSrc(team)} />
      <span data-en={side} data-ko={sideKo}>
        {side}
      </span>
      <strong>{team.name}</strong>
      <small>{pitcher ?? "TBD"}</small>
    </div>
  );
}

function lineupState(game: RecentGame): LineupState {
  if (game.scheduler?.batting_lineup_missing === false) {
    return {
      label: "Lineup ready",
      labelKo: "라인업 준비",
      detail: "Scheduler metadata says the batting lineup was available before submission.",
      detailKo: "스케줄러 메타데이터상 제출 전 타자 라인업이 준비됨.",
      tone: "good",
    };
  }
  if (game.scheduler?.starter_confirmed === true) {
    return {
      label: "Pitchers confirmed",
      labelKo: "선발 확인",
      detail: "Starting pitchers were available, but the full batting order was still missing.",
      detailKo: "선발투수는 확인됐지만 전체 타순은 아직 부족했음.",
      tone: "warn",
    };
  }
  if (starterName(game, "home") && starterName(game, "away")) {
    return {
      label: "Starters published",
      labelKo: "선발 공개",
      detail: "The public result row carries both starter names from the submitted game.",
      detailKo: "공개 결과 행에 제출 경기의 양팀 선발명이 포함됨.",
      tone: "neutral",
    };
  }
  return {
    label: "Pending",
    labelKo: "대기",
    detail: "No public starter or lineup metadata is available for this row yet.",
    detailKo: "이 행에는 아직 공개 선발/라인업 메타데이터가 없음.",
    tone: "neutral",
  };
}

function starterName(game: RecentGame, side: "home" | "away"): string | null {
  const value =
    side === "home"
      ? (game.home_sp_name ?? game.scheduler?.home_sp_name)
      : (game.away_sp_name ?? game.scheduler?.away_sp_name);
  const trimmed = value?.trim();
  return trimmed ? trimmed : null;
}

function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : String(value);
}
