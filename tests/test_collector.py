from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src import collector as collector_module
from src.collector import DataCollector
from src.constants import GAME_STATE_FINISHED, LEAGUE_TYPE_REGULAR


def _complete_lineup_payload() -> dict[str, list[dict[str, Any]]]:
    return {
        "1001": [
            {
                "s_no": 2026061301,
                "t_code": 1001,
                "p_no": 100100 + i,
                "position": 2,
                "starting": "Y",
                "battingOrder": i + 1,
            }
            for i in range(9)
        ],
        "2002": [
            {
                "s_no": 2026061301,
                "t_code": 2002,
                "p_no": 200200 + i,
                "position": 2,
                "starting": "Y",
                "battingOrder": i + 1,
            }
            for i in range(9)
        ],
    }


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((endpoint, params))

        if endpoint == "/prediction/gameSchedule":
            return {
                "0613": [
                    {
                        "s_no": 2026061301,
                        "leagueType": LEAGUE_TYPE_REGULAR,
                        "state": GAME_STATE_FINISHED,
                    }
                ]
            }
        if endpoint == "/prediction/gameBoxscore":
            return {"s_no": params["s_no"], "home_score": 5, "away_score": 3}
        if endpoint == "/prediction/gameLineup":
            return {"1001": [], "2002": []}

        raise AssertionError(f"unexpected endpoint: {endpoint}")


def test_collect_daily_all_force_refresh_overwrites_cached_game_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(collector_module, "RAW_DIR", str(tmp_path / "raw"))

    raw_year = tmp_path / "raw" / "2026"
    schedule_path = raw_year / "schedule" / "2026-06-13.json"
    boxscore_path = raw_year / "boxscore" / "2026061301.json"
    lineup_path = raw_year / "lineup" / "2026061301.json"

    schedule_path.parent.mkdir(parents=True)
    boxscore_path.parent.mkdir(parents=True)
    lineup_path.parent.mkdir(parents=True)

    schedule_path.write_text(
        json.dumps({"0613": [{"s_no": 2026061301, "leagueType": LEAGUE_TYPE_REGULAR}]}),
        encoding="utf-8",
    )
    boxscore_path.write_text(
        json.dumps({"s_no": 2026061301, "home_score": None, "away_score": None}),
        encoding="utf-8",
    )
    lineup_path.write_text(json.dumps({"1001": []}), encoding="utf-8")

    collector = DataCollector.__new__(DataCollector)
    collector._client = FakeClient()

    collector.collect_daily_all(2026, 6, 13, force=True)

    assert json.loads(boxscore_path.read_text(encoding="utf-8"))["home_score"] == 5
    assert json.loads(lineup_path.read_text(encoding="utf-8"))["2002"] == []
    assert [call[0] for call in collector._client.calls] == [
        "/prediction/gameSchedule",
        "/prediction/gameBoxscore",
        "/prediction/gameLineup",
    ]


def test_collect_lineup_refreshes_incomplete_cached_lineup(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(collector_module, "RAW_DIR", str(tmp_path / "raw"))
    lineup_path = tmp_path / "raw" / "2026" / "lineup" / "2026061301.json"
    lineup_path.parent.mkdir(parents=True)
    lineup_path.write_text(json.dumps({"1001": [], "2002": []}), encoding="utf-8")

    collector = DataCollector.__new__(DataCollector)
    collector._client = FakeClient()

    collector.collect_lineup(2026061301, 2026)

    assert json.loads(lineup_path.read_text(encoding="utf-8"))["2002"] == []
    assert collector._client.calls == [
        ("/prediction/gameLineup", {"s_no": 2026061301})
    ]


def test_collect_lineup_reuses_complete_cached_lineup(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(collector_module, "RAW_DIR", str(tmp_path / "raw"))
    lineup_path = tmp_path / "raw" / "2026" / "lineup" / "2026061301.json"
    lineup_path.parent.mkdir(parents=True)
    lineup_path.write_text(json.dumps(_complete_lineup_payload()), encoding="utf-8")

    collector = DataCollector.__new__(DataCollector)
    collector._client = FakeClient()

    lineup = collector.collect_lineup(2026061301, 2026)

    assert lineup["1001"][0]["p_no"] == 100100
    assert collector._client.calls == []
