import { readFile } from "node:fs/promises";
import path from "node:path";

export type TeamInfo = {
  name: string;
  logo_key: string;
};

export type SchedulerSummary = {
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

export type RecentGame = {
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

export type DashboardData = {
  schema_version?: number;
  generated_at: string;
  model_version?: string | null;
  recent_games?: RecentGame[];
  results: unknown[];
};

export type TopFeature = {
  feature: string;
  value: number;
};

export type FeatureAnalysisSection = {
  id: string;
  title: string;
  description: string;
  image_path: string;
  csv_path: string;
};

export type FeatureAnalysisManifest = {
  generated_at: string;
  model_version: string | null;
  task_type?: string;
  sample_size: number;
  years?: number[];
  sections?: FeatureAnalysisSection[];
  top_features?: {
    gain?: TopFeature[];
    split?: TopFeature[];
    shap?: TopFeature[];
  };
};

const RESULTS_FILE = path.join(process.cwd(), "public", "results.json");
const FEATURE_MANIFEST_FILE = path.join(
  process.cwd(),
  "public",
  "feature-analysis",
  "manifest.json",
);

export async function loadPublicDashboardData(): Promise<DashboardData> {
  const parsed = JSON.parse(await readFile(RESULTS_FILE, "utf8")) as unknown;
  if (!isDashboardData(parsed)) {
    throw new Error("Invalid public dashboard data.");
  }
  return parsed;
}

export async function loadFeatureAnalysisManifest(): Promise<FeatureAnalysisManifest | null> {
  try {
    const parsed = JSON.parse(await readFile(FEATURE_MANIFEST_FILE, "utf8")) as unknown;
    return isFeatureAnalysisManifest(parsed) ? parsed : null;
  } catch (error) {
    if (isMissingFileError(error)) {
      return null;
    }
    throw error;
  }
}

export function sortedRecentGames(data: DashboardData): RecentGame[] {
  return [...(data.recent_games ?? [])].sort((a, b) => {
    const dateOrder = (b.game_date ?? "").localeCompare(a.game_date ?? "");
    if (dateOrder !== 0) {
      return dateOrder;
    }
    return (b.s_no ?? 0) - (a.s_no ?? 0);
  });
}

export function teamLogoSrc(team: TeamInfo): string {
  return `/team-logos/${team.logo_key}.svg`;
}

export function formatDateLabel(value: string | null): string {
  if (!value) {
    return "n/a";
  }
  const [year, month, day] = value.split("T")[0].split("-").map(Number);
  if (!year || !month || !day) {
    return value;
  }
  return `${month}.${day}`;
}

export function formatTimeLabel(value: string | null): string {
  if (!value) {
    return "n/a";
  }
  const [hour, minute] = value.split(":");
  return hour && minute ? `${hour}:${minute}` : value;
}

export function formatRate(value: number | null, digits = 1): string {
  return value === null ? "n/a" : `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null, digits = 1): string {
  return value === null || Number.isNaN(value) ? "n/a" : value.toFixed(digits);
}

export function formatProbability(value: number | null): string {
  return value === null ? "n/a" : `${value.toFixed(2)}%`;
}

function isDashboardData(value: unknown): value is DashboardData {
  return isRecord(value) && typeof value.generated_at === "string" && Array.isArray(value.results);
}

function isFeatureAnalysisManifest(value: unknown): value is FeatureAnalysisManifest {
  return (
    isRecord(value) &&
    typeof value.generated_at === "string" &&
    typeof value.sample_size === "number"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isMissingFileError(error: unknown): boolean {
  return isRecord(error) && error.code === "ENOENT";
}
