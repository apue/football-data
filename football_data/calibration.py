from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from football_data.editorial import (
    DEFAULT_SCORING_CONFIG,
    _load_scoring_config,
    _player_rows_for_date,
    _score_player,
)


def build_potm_calibration_report(
    *,
    db_path: str | Path,
    labels_path: str | Path,
    match_date: str,
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
    top_n: int = 3,
) -> dict[str, Any]:
    scoring = _load_scoring_config(scoring_config_path)
    labels = _load_potm_labels(labels_path, match_date=match_date)
    rankings = _rank_players_by_match(db_path, match_date, scoring)
    items = [_calibration_item(label, rankings, top_n=top_n) for label in labels]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": match_date,
        "scoring_version": scoring["version"],
        "top_n": top_n,
        "summary": _summary(items, top_n=top_n),
        "items": items,
    }


def discover_potm_evidence_candidates(
    *,
    db_path: str | Path,
    match_date: str,
    search_fn: Callable[[str, int], list[dict[str, str]]] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    matches = _matches_for_date(db_path, match_date)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": match_date,
        "limit": limit,
        "matches": [
            _discover_match_candidates(match, search_fn=search_fn, limit=limit)
            for match in matches
        ],
    }


def render_potm_calibration_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# POTM Calibration - {report['match_date']}",
        "",
        f"Scoring version: `{report['scoring_version']}`",
        "",
        "FIFA POTM is a weak label. Use this report for calibration and sanity checks, not as a direct scoring input.",
        "",
        "## Summary",
        "",
        f"- Labels: {report['summary']['label_count']}",
        f"- Top-{report['top_n']} hit rate: {report['summary']['top3_hit_rate']:.2f}",
        f"- Median POTM rank: {report['summary']['median_potm_rank']}",
        f"- Worst rank diff: {report['summary']['worst_rank_diff']}",
        "",
        "## Matches",
        "",
    ]
    for item in report["items"]:
        lines.extend(
            [
                f"### Match {item['match_no']}: {item['potm_player_name']}",
                "",
                f"- Status: `{item['status']}`",
                f"- Model rank: rank {item['model_rank']}" if item["model_rank"] else "- Model rank: missing",
                f"- Rank diff: {item['rank_diff']}" if item["rank_diff"] is not None else "- Rank diff: n/a",
                f"- Source: {item.get('source_url') or 'n/a'}",
                "- Top model players: "
                + ", ".join(
                    f"{player['rank']}. {player['player_name']} ({player['team']})"
                    for player in item["top_model_players"]
                ),
            ]
        )
        if item["possible_missing_signals"]:
            lines.append("- Possible missing signals: " + ", ".join(item["possible_missing_signals"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _matches_for_date(db_path: str | Path, match_date: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            select match_no, match_key, home_team, away_team
            from matches
            where match_date = ?
            order by match_no
            """,
            (match_date,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _discover_match_candidates(
    match: dict[str, Any],
    *,
    search_fn: Callable[[str, int], list[dict[str, str]]] | None,
    limit: int,
) -> dict[str, Any]:
    queries = _potm_search_queries(match)
    seen_urls: set[str] = set()
    results: list[dict[str, str]] = []
    if search_fn:
        for query in queries:
            for result in search_fn(query, limit):
                url = result.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                results.append(
                    {
                        "query": query,
                        "title": result.get("title", ""),
                        "url": url,
                        "description": result.get("description", ""),
                    }
                )
    return {
        "match_no": match["match_no"],
        "match_key": match["match_key"],
        "home_team": match["home_team"],
        "away_team": match["away_team"],
        "queries": queries,
        "results": results,
    }


def _potm_search_queries(match: dict[str, Any]) -> list[str]:
    home = match["home_team"]
    away = match["away_team"]
    match_no = int(match["match_no"])
    return [
        f"FIFA World Cup 2026 Match {match_no} {home} {away} Player of the Match",
        f"{home} {away} FIFA 2026 player of the match POTM",
    ]


def _load_potm_labels(labels_path: str | Path, *, match_date: str) -> list[dict[str, Any]]:
    path = Path(labels_path)
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    labels = payload.get("labels", [])
    if not isinstance(labels, list):
        raise ValueError("POTM labels file must contain a labels list.")
    return [
        label
        for label in labels
        if not label.get("match_date") or str(label.get("match_date")) == match_date
    ]


def _rank_players_by_match(
    db_path: str | Path,
    match_date: str,
    scoring: dict[str, Any],
) -> dict[int, list[dict[str, Any]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        players = [_score_player(row, scoring) for row in _player_rows_for_date(conn, match_date)]
    finally:
        conn.close()
    rankings: dict[int, list[dict[str, Any]]] = {}
    for player in players:
        rankings.setdefault(int(player["match_no"]), []).append(player)
    for match_no, match_players in rankings.items():
        match_players.sort(key=lambda player: player["composite_score"], reverse=True)
        for rank, player in enumerate(match_players, start=1):
            player["model_rank"] = rank
    return rankings


def _calibration_item(
    label: dict[str, Any],
    rankings: dict[int, list[dict[str, Any]]],
    *,
    top_n: int,
) -> dict[str, Any]:
    match_no = int(label["match_no"])
    players = rankings.get(match_no, [])
    potm_name = str(label["potm_player_name"])
    potm = _find_player(players, potm_name)
    model_rank = int(potm["model_rank"]) if potm else None
    rank_diff = model_rank - 1 if model_rank else None
    top_model_players = [_public_player(player) for player in players[:top_n]]
    return {
        "match_no": match_no,
        "match_key": label.get("match_key"),
        "potm_player_name": potm_name,
        "source_url": label.get("source_url"),
        "source_type": label.get("source_type"),
        "confidence": label.get("confidence"),
        "model_rank": model_rank,
        "rank_diff": rank_diff,
        "status": _status(model_rank, top_n=top_n),
        "top_model_players": top_model_players,
        "possible_missing_signals": _possible_missing_signals(label, potm),
    }


def _find_player(players: list[dict[str, Any]], player_name: str) -> dict[str, Any] | None:
    wanted = _normalize_name(player_name)
    for player in players:
        if _normalize_name(str(player["player_name"])) == wanted:
            return player
    return None


def _normalize_name(name: str) -> str:
    return " ".join(name.upper().replace(".", "").split())


def _public_player(player: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": player["model_rank"],
        "player_name": player["player_name"],
        "team": player["team"],
        "composite_score": player["composite_score"],
    }


def _status(model_rank: int | None, *, top_n: int) -> str:
    if model_rank is None:
        return "missing"
    if model_rank <= top_n:
        return "ok"
    if model_rank <= top_n + 2:
        return "warning"
    return "red_flag"


def _possible_missing_signals(
    label: dict[str, Any],
    potm: dict[str, Any] | None,
) -> list[str]:
    text = " ".join(
        str(label.get(key) or "")
        for key in ("notes", "source_title", "source_excerpt")
    ).lower()
    signals: list[str] = []
    if any(token in text for token in ("stoppage", "90+", "94", "95", "late", "winner")):
        signals.append("late_match_winner")
    if "assist" in text:
        signals.append("assist_or_goal_involvement")
    if potm and int(potm.get("goals") or 0) > 0 and potm.get("model_rank", 999) > 3:
        signals.append("game_state_goal_value")
    return signals


def _summary(items: list[dict[str, Any]], *, top_n: int) -> dict[str, Any]:
    ranks = [item["model_rank"] for item in items if item["model_rank"] is not None]
    hit_count = sum(1 for rank in ranks if rank <= top_n)
    diffs = [item["rank_diff"] for item in items if item["rank_diff"] is not None]
    return {
        "label_count": len(items),
        "top3_hit_rate": round(hit_count / len(items), 4) if items else 0.0,
        "median_potm_rank": _median(ranks),
        "worst_rank_diff": max(diffs) if diffs else None,
    }


def _median(values: list[int]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    midpoint = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return float(sorted_values[midpoint])
    return (sorted_values[midpoint - 1] + sorted_values[midpoint]) / 2
