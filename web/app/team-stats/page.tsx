import {
  formatDateLabel,
  formatNumber,
  formatProbability,
  formatRate,
  loadPublicDashboardData,
  sortedRecentGames,
  teamLogoSrc,
  type RecentGame,
  type TeamInfo,
} from "../public-data";

type TeamSummary = {
  team: TeamInfo;
  submittedGames: number;
  finalizedGames: number;
  wins: number;
  losses: number;
  runsFor: number;
  runsAgainst: number;
  probabilityTotal: number;
  probabilityGames: number;
  modelLeans: number;
  latestGameDate: string | null;
};

export const dynamic = "force-static";

export default async function TeamStatsPage() {
  const data = await loadPublicDashboardData();
  const games = sortedRecentGames(data);
  const summaries = buildTeamSummaries(games);
  const finalizedGames = games.filter((game) => game.game_status === "final");
  const topTeams = summaries
    .filter((summary) => summary.finalizedGames > 0)
    .slice()
    .sort((a, b) => winRateValue(b) - winRateValue(a) || b.finalizedGames - a.finalizedGames)
    .slice(0, 4);

  return (
    <main className="dashboard-shell">
      <section className="feature-page-heading">
        <div>
          <p className="eyebrow" data-en="Team stats" data-ko="팀 지표">
            Team stats
          </p>
          <h1 data-en="Recent team form from public games" data-ko="공개 경기 기준 최근 팀 흐름">
            Recent team form from public games
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

      <section className="metric-grid" aria-label="Team stats facts">
        <article className="metric-card">
          <span data-en="Public games" data-ko="공개 경기">
            Public games
          </span>
          <strong>{games.length}</strong>
          <p data-en="Submitted games in results.json" data-ko="results.json에 게시된 제출 경기">
            Submitted games in results.json
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Finalized" data-ko="확정">
            Finalized
          </span>
          <strong>{finalizedGames.length}</strong>
          <p data-en="Cancelled games are excluded from records" data-ko="취소 경기는 전적 계산에서 제외함">
            Cancelled games are excluded from records
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Teams" data-ko="팀">
            Teams
          </span>
          <strong>{summaries.length}</strong>
          <p data-en="Teams seen in the recent public window" data-ko="최근 공개 구간에 등장한 팀">
            Teams seen in the recent public window
          </p>
        </article>
        <article className="metric-card">
          <span data-en="Model" data-ko="모델">
            Model
          </span>
          <strong>{data.model_version ?? "n/a"}</strong>
          <p data-en="Public prediction version" data-ko="공개 예측 모델 버전">
            Public prediction version
          </p>
        </article>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="Current leaders" data-ko="최근 상위 팀">
              Current leaders
            </p>
            <p
              data-en="Records and run averages come only from finalized public submitted games."
              data-ko="전적과 득실 평균은 확정된 공개 제출 경기만 기준으로 계산함."
            >
              Records and run averages come only from finalized public submitted games.
            </p>
          </div>
        </div>
        <div className="team-stat-card-grid">
          {topTeams.map((summary) => (
            <article className="team-stat-card" key={summary.team.logo_key}>
              <div className="team-stat-head">
                <img alt="" src={teamLogoSrc(summary.team)} />
                <div>
                  <strong>{summary.team.name}</strong>
                  <span>
                    {summary.wins}-{summary.losses} · {formatRate(winRate(summary))}
                  </span>
                </div>
              </div>
              <dl className="detail-stat-list">
                <div>
                  <dt data-en="Runs for" data-ko="평균 득점">
                    Runs for
                  </dt>
                  <dd>{formatNumber(averageRunsFor(summary))}</dd>
                </div>
                <div>
                  <dt data-en="Runs against" data-ko="평균 실점">
                    Runs against
                  </dt>
                  <dd>{formatNumber(averageRunsAgainst(summary))}</dd>
                </div>
                <div>
                  <dt data-en="Avg model lean" data-ko="평균 모델 확률">
                    Avg model lean
                  </dt>
                  <dd>{formatProbability(averageProbability(summary))}</dd>
                </div>
                <div>
                  <dt data-en="Latest" data-ko="최근">
                    Latest
                  </dt>
                  <dd>{formatDateLabel(summary.latestGameDate)}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="guide-section">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow" data-en="All teams" data-ko="전체 팀">
              All teams
            </p>
          </div>
        </div>
        <div className="guide-feature-table-wrap">
          <table className="guide-feature-table team-stat-table">
            <thead>
              <tr>
                <th data-en="Team" data-ko="팀">Team</th>
                <th data-en="Record" data-ko="전적">Record</th>
                <th data-en="Win rate" data-ko="승률">Win rate</th>
                <th data-en="RF/G" data-ko="득점/G">RF/G</th>
                <th data-en="RA/G" data-ko="실점/G">RA/G</th>
                <th data-en="Model lean" data-ko="모델 확률">Model lean</th>
                <th data-en="Submitted games" data-ko="제출 경기">Submitted games</th>
              </tr>
            </thead>
            <tbody>
              {summaries.map((summary) => (
                <tr key={summary.team.logo_key}>
                  <td>
                    <span className="table-team">
                      <img alt="" src={teamLogoSrc(summary.team)} />
                      <strong>{summary.team.name}</strong>
                    </span>
                  </td>
                  <td>{summary.wins}-{summary.losses}</td>
                  <td>{formatRate(winRate(summary))}</td>
                  <td>{formatNumber(averageRunsFor(summary))}</td>
                  <td>{formatNumber(averageRunsAgainst(summary))}</td>
                  <td>{formatProbability(averageProbability(summary))}</td>
                  <td>{summary.submittedGames}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="feature-note">
        <strong data-en="Data boundary" data-ko="데이터 경계">
          Data boundary
        </strong>
        <p
          data-en="This page summarizes the public submitted-game window, not the private feature matrix. Model training still uses strict pre-game features only."
          data-ko="이 페이지는 공개 제출 경기 구간을 요약하며, 비공개 feature matrix를 노출하지 않음. 모델 학습은 여전히 경기 전 feature만 사용함."
        >
          This page summarizes the public submitted-game window, not the private feature matrix.
          Model training still uses strict pre-game features only.
        </p>
      </section>
    </main>
  );
}

function buildTeamSummaries(games: RecentGame[]): TeamSummary[] {
  const summaries = new Map<string, TeamSummary>();
  for (const game of games) {
    updateTeamSummary(summaries, game, "home");
    updateTeamSummary(summaries, game, "away");
  }
  return [...summaries.values()].sort(
    (a, b) => b.submittedGames - a.submittedGames || a.team.name.localeCompare(b.team.name),
  );
}

function updateTeamSummary(
  summaries: Map<string, TeamSummary>,
  game: RecentGame,
  side: "home" | "away",
): void {
  const team = side === "home" ? game.home_team : game.away_team;
  const summary = summaries.get(team.logo_key) ?? createTeamSummary(team);
  summary.submittedGames += 1;
  summary.latestGameDate = maxDate(summary.latestGameDate, game.game_date);

  if (game.probability_published && game.home_win_probability !== null) {
    summary.probabilityTotal += side === "home" ? game.home_win_probability : 100 - game.home_win_probability;
    summary.probabilityGames += 1;
  }
  if (game.predicted_winner === side) {
    summary.modelLeans += 1;
  }
  if (game.game_status === "final" && game.home_score !== null && game.away_score !== null) {
    summary.finalizedGames += 1;
    summary.runsFor += side === "home" ? game.home_score : game.away_score;
    summary.runsAgainst += side === "home" ? game.away_score : game.home_score;
    if (game.actual_winner === side) {
      summary.wins += 1;
    } else {
      summary.losses += 1;
    }
  }
  summaries.set(team.logo_key, summary);
}

function createTeamSummary(team: TeamInfo): TeamSummary {
  return {
    team,
    submittedGames: 0,
    finalizedGames: 0,
    wins: 0,
    losses: 0,
    runsFor: 0,
    runsAgainst: 0,
    probabilityTotal: 0,
    probabilityGames: 0,
    modelLeans: 0,
    latestGameDate: null,
  };
}

function winRate(summary: TeamSummary): number | null {
  return summary.finalizedGames === 0 ? null : summary.wins / summary.finalizedGames;
}

function winRateValue(summary: TeamSummary): number {
  return winRate(summary) ?? 0;
}

function averageRunsFor(summary: TeamSummary): number | null {
  return summary.finalizedGames === 0 ? null : summary.runsFor / summary.finalizedGames;
}

function averageRunsAgainst(summary: TeamSummary): number | null {
  return summary.finalizedGames === 0 ? null : summary.runsAgainst / summary.finalizedGames;
}

function averageProbability(summary: TeamSummary): number | null {
  return summary.probabilityGames === 0 ? null : summary.probabilityTotal / summary.probabilityGames;
}

function maxDate(current: string | null, next: string | null): string | null {
  if (!current) {
    return next;
  }
  if (!next) {
    return current;
  }
  return next > current ? next : current;
}
