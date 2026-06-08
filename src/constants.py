"""
Constants for Statiz KBO prediction system.
Team codes, stadium codes, and API parameter values from the official API_CODE sheet.
"""

# ─── Team codes (t_code) ────────────────────────────────────────────────────
TEAM_CODES: dict[int, str] = {
    1001: "삼성",
    2002: "KIA",
    3001: "롯데",
    5002: "LG",
    6002: "두산",
    7002: "한화",
    9002: "SSG",
    10001: "키움",
    11001: "NC",
    12001: "KT",
}

# ─── Stadium codes (s_code) ─────────────────────────────────────────────────
STADIUM_CODES: dict[int, str] = {
    1001: "잠실",
    1002: "목동",
    1003: "고척",
    1004: "동대문",
    2001: "인천",
    2002: "수원",
    2003: "숭의",
    3001: "청주",
    4001: "한밭",
    4003: "대전",
    5001: "군산",
    6001: "광주",
    7002: "포항",
    7003: "대구",
    8001: "사직",
    8003: "울산",
    8005: "창원",
}

# ─── League types (leagueType) ───────────────────────────────────────────────
LEAGUE_TYPE_REGULAR = 10100
LEAGUE_TYPE_POSTSEASON = 10200
LEAGUE_TYPE_KOREAN_SERIES = 10201
LEAGUE_TYPE_PLAYOFF = 10202
LEAGUE_TYPE_SEMI_PLAYOFF = 10203
LEAGUE_TYPE_WILDCARD = 10204
LEAGUE_TYPE_PRESEASON = 10400

# ─── Game states (s_state) ──────────────────────────────────────────────────
GAME_STATE_BEFORE = 1  # 경기 전
GAME_STATE_IN_PROGRESS = 2  # 경기 중
GAME_STATE_FINISHED = 3  # 경기 종료
GAME_STATE_CANCELLED = 4  # 경기 취소
GAME_STATE_RAINOUT_COLD = 5  # 강우 콜드

# ─── teamRecord API parameter values ────────────────────────────────────────
TEAM_RECORD_BATTING = "batting"
TEAM_RECORD_PITCHING = "pitching"

# Period (pe) parameter values for teamRecord
PERIOD_ALL = ""  # 전체 (default)
PERIOD_LAST_30 = "D30"
PERIOD_FIRST_HALF = "F"
PERIOD_SECOND_HALF = "S"
PERIOD_MARCH = "M3"
PERIOD_APRIL = "M4"
PERIOD_MAY = "M5"
PERIOD_JUNE = "M6"
PERIOD_JULY = "M7"
PERIOD_AUGUST = "M8"
PERIOD_SEPTEMBER = "M9"
PERIOD_OCTOBER = "M10"

# Day of week (we) parameter values
WEEKDAY_ALL = ""  # 전체 (default)

# Home/Away (ha) parameter values
HA_ALL = ""
HA_HOME = "H"
HA_AWAY = "N"

# ─── Roster code parameter ───────────────────────────────────────────────────
ROSTER_CODE_1ST_TEAM = 1  # 1군
ROSTER_CODE_2ND_TEAM = 2  # 2군

# ─── Supported seasons ───────────────────────────────────────────────────────
SUPPORTED_YEARS = [2023, 2024, 2025]

# ─── File paths ──────────────────────────────────────────────────────────────
DATA_DIR = "data"
RAW_DIR = f"{DATA_DIR}/raw"
CLEAN_DIR = f"{DATA_DIR}/clean"
FEATURES_DIR = f"{DATA_DIR}/features"
ARTIFACTS_DIR = "artifacts"
MODEL_REGISTRY_DIR = f"{ARTIFACTS_DIR}/model_registry"
LOGS_DIR = "logs"

GAMES_CSV = f"{CLEAN_DIR}/games.csv"
LINEUP_SNAPSHOT_CSV = f"{CLEAN_DIR}/lineup_snapshot.csv"
PREDICTION_LOG_CSV = f"{LOGS_DIR}/prediction_log.csv"
SUBMISSION_LOG_CSV = f"{LOGS_DIR}/submission_log.csv"


def feature_csv_path(year: int) -> str:
    """Return path to feature CSV for a given year."""
    return f"{FEATURES_DIR}/feature_game_pre_match_{year}.csv"
