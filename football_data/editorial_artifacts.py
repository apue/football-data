from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from football_data.editorial_constants import AWARD_LABELS
from football_data.editorial_copy import content_html
from football_data.flags import format_player, format_team


def build_compiled_report(
    *,
    experiment: dict[str, Any],
    rankings: dict[str, Any],
    candidate_pool: dict[str, Any],
    selection_decision: dict[str, Any],
    selection_validation: dict[str, Any],
    copy: dict[str, Any],
    editorial_loop_summary: dict[str, Any] | None = None,
    editorial_loop_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = {
        str(candidate["player_id"]): candidate
        for candidate in candidate_pool.get("selectable_candidates", [])
    }
    copy_by_language = {
        language: {
            str(item["player_id"]): item
            for item in payload.get("items", [])
            if isinstance(item, dict)
        }
        for language, payload in copy.items()
    }
    uses_goal_involvements = _uses_goal_involvements(rankings)
    event_sources = _event_sources(rankings, uses_goal_involvements=uses_goal_involvements)
    choices = []
    for selected in selection_decision.get("selected", []):
        candidate = candidates[str(selected["player_id"])]
        award_type = str(selected["award_type"])
        award_context = (candidate.get("award_contexts") or {}).get(award_type) or {}
        en = copy_by_language.get("en", {}).get(candidate["player_id"], {})
        zh = copy_by_language.get("zh", {}).get(candidate["player_id"], {})
        choices.append(
            {
                "award_type": award_type,
                "award_types": [award_type],
                "award_label": AWARD_LABELS.get(award_type, {"en": award_type, "zh": award_type}),
                "player_id": candidate["player_id"],
                "player_name": candidate["player_name"],
                "team": candidate["team"],
                "opponent": candidate["opponent"],
                "match_key": candidate["match_key"],
                "match_no": candidate["match_no"],
                "player_no": candidate["player_no"],
                "position": candidate.get("position"),
                "score": candidate.get("headline_score"),
                "metrics": award_context.get("metrics", candidate.get("metrics", {})),
                "evidence_chips": award_context.get(
                    "evidence_chips",
                    candidate.get("evidence_chips", {"en": [], "zh": []}),
                ),
                "selection_reason": selected.get("editorial_reason"),
                "content": {
                    "en": {
                        "title": en.get("title") or f"{candidate['player_name']} made the edit",
                        "html": content_html(en.get("body") or selected.get("editorial_reason") or ""),
                    },
                    "zh": {
                        "title": zh.get("title") or f"{candidate['player_name']} 入选",
                        "html": content_html(zh.get("body") or selected.get("editorial_reason") or ""),
                    },
                },
            }
        )
    return {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "compiled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": rankings["match_date"],
        "scoring_version": rankings["scoring_version"],
        "editorial_generation": {
            "workflow_variant": experiment["workflow_variant"],
            "experiment_id": experiment["id"],
            "selection_mode": experiment["selection"]["mode"],
            "selection_review_profile": experiment.get("selection_review_profile"),
            "copy_review_profile": experiment.get("copy_review_profile"),
            "loop_policy": experiment.get("loop_policy"),
            "editorial_loop_status": (editorial_loop_validation or {}).get("status"),
            "selection_rounds": ((editorial_loop_summary or {}).get("selection_loop") or {}).get("rounds"),
            "copy_rounds": ((editorial_loop_summary or {}).get("copy_loop") or {}).get("rounds"),
            "uses_official_assists": uses_goal_involvements,
            "uses_goal_involvements": uses_goal_involvements,
            "event_source": "fifa_timeline_api" if uses_goal_involvements else None,
            "event_sources": event_sources,
        },
        "matches": rankings["matches"],
        "match_flows": rankings.get("match_flows", {}),
        "choices": choices,
        "selection_validation": selection_validation,
        "audit": [],
    }


def write_v2_artifacts(
    *,
    compiled: dict[str, Any],
    rankings: dict[str, Any],
    candidate_pool: dict[str, Any],
    selector_input: dict[str, Any],
    selection_decision: dict[str, Any],
    selection_validation: dict[str, Any],
    copy_payload: dict[str, Any],
    copy: dict[str, Any],
    run_payload: dict[str, Any],
    site_dir: str | Path,
    reports_dir: str | Path,
    agent_runs_dir: str | Path,
    run_out_path: str | Path,
    copy_validation: dict[str, Any] | None = None,
    editorial_loop_summary: dict[str, Any] | None = None,
    editorial_loop_validation: dict[str, Any] | None = None,
) -> None:
    write_compiled_editorial_artifacts(compiled, site_dir)
    reports_path = Path(reports_dir) / "editorial"
    reports_path.mkdir(parents=True, exist_ok=True)
    _remove_retired_sidecars(site_dir, reports_path, compiled["match_date"])
    (reports_path / f"{compiled['match_date']}.md").write_text(
        _markdown_report(compiled),
        encoding="utf-8",
    )
    audit_dir = Path(agent_runs_dir) / compiled["match_date"]
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_payloads = {
        "rankings": _audit_rankings(rankings),
        "candidate_pool": candidate_pool,
        "selector_input": selector_input,
        "selection_decision": selection_decision,
        "selection_validation": selection_validation,
        "copy_payload": copy_payload,
        "copy": copy,
        "run": run_payload,
    }
    if copy_validation is not None:
        audit_payloads["copy_validation"] = copy_validation
    if editorial_loop_summary is not None:
        audit_payloads["editorial_loop_summary"] = editorial_loop_summary
    if editorial_loop_validation is not None:
        audit_payloads["editorial_loop_validation"] = editorial_loop_validation
    for name, payload in audit_payloads.items():
        (audit_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    out = Path(run_out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _markdown_report(compiled: dict[str, Any]) -> str:
    lines = [
        f"# Editor's Choices - {compiled['match_date']}",
        "",
        f"Workflow: `{compiled['editorial_generation']['workflow_variant']}`",
        f"Scoring version: `{compiled['scoring_version']}`",
        "",
        "## Choices",
        "",
    ]
    for choice in compiled["choices"]:
        lines.extend(
            [
                f"### {choice['award_label']['en']}: {choice['player_name']}",
                "",
                f"- Team: {choice['team']}",
                f"- Reason: {choice.get('selection_reason')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _audit_rankings(rankings: dict[str, Any]) -> dict[str, Any]:
    role_rankings = rankings.get("rankings", {}).get("roles", {})
    return {
        "schema_version": 1,
        "match_date": rankings.get("match_date"),
        "scoring_version": rankings.get("scoring_version"),
        "event_sources": rankings.get("event_sources", {}),
        "matches": rankings.get("matches", []),
        "match_flows": rankings.get("match_flows", {}),
        "rankings": {
            "headline": list(rankings.get("rankings", {}).get("headline", []))[:50],
            "roles": {
                role: list(items)[:25]
                for role, items in role_rankings.items()
            },
        },
        "rank_lookup": {
            str(player.get("player_id")): {
                "player_name": player.get("player_name"),
                "team": player.get("team"),
                "match_no": player.get("match_no"),
                "headline_rank": player.get("headline_rank"),
                "headline_score": player.get("headline_score"),
                "role_ranks": {
                    key.removesuffix("_rank"): value
                    for key, value in player.items()
                    if key.endswith("_rank")
                },
            }
            for player in rankings.get("players", [])
            if isinstance(player, dict) and player.get("player_id")
        },
    }


def _uses_goal_involvements(rankings: dict[str, Any]) -> bool:
    event_sources = rankings.get("event_sources")
    if isinstance(event_sources, dict) and event_sources.get("goal_involvements"):
        return event_sources.get("goal_involvements") == "fifa_timeline_api"
    return str(rankings.get("scoring_version") or "") == "v0.4"


def _event_sources(rankings: dict[str, Any], *, uses_goal_involvements: bool) -> dict[str, str]:
    event_sources = rankings.get("event_sources")
    if isinstance(event_sources, dict):
        return {str(key): str(value) for key, value in event_sources.items()}
    if uses_goal_involvements:
        return {"goal_involvements": "fifa_timeline_api"}
    return {}


def _remove_retired_sidecars(
    site_dir: str | Path,
    reports_path: Path,
    match_date: str,
) -> None:
    dated_path = Path(site_dir) / "editorial" / match_date
    for filename in (
        "evidence.json",
        "fact_bank.zh.json",
        "brief.en.json",
        "external_evidence.json",
    ):
        path = dated_path / filename
        if path.exists():
            path.unlink()


def write_compiled_editorial_artifacts(
    compiled: dict[str, Any],
    site_dir: str | Path = "site",
) -> None:
    site_path = Path(site_dir)
    editorial_path = site_path / "editorial"
    dated_path = editorial_path / compiled["match_date"]
    dated_path.mkdir(parents=True, exist_ok=True)
    editorial_path.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(compiled, ensure_ascii=False, indent=2) + "\n"
    (dated_path / "choices.json").write_text(json_text, encoding="utf-8")
    (dated_path / "index.html").write_text(_render_editorial_page(compiled), encoding="utf-8")
    latest = _latest_editorial_report(editorial_path, compiled)
    (editorial_path / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    archive_items = _editorial_archive_items(editorial_path, compiled)
    (editorial_path / "index.html").write_text(
        _render_editorial_index(archive_items),
        encoding="utf-8",
    )


def _latest_editorial_report(editorial_path: Path, current: dict[str, Any]) -> dict[str, Any]:
    reports = [current]
    latest = _load_json(editorial_path / "latest.json")
    if latest:
        reports.append(latest)
    for choices_path in editorial_path.glob("*/choices.json"):
        report = _load_json(choices_path)
        if report:
            reports.append(report)
    return max(reports, key=lambda report: str(report.get("match_date") or ""))


def _editorial_archive_items(
    editorial_path: Path,
    current: dict[str, Any],
) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, Any]] = {}
    for choices_path in editorial_path.glob("*/choices.json"):
        report = _load_json(choices_path)
        match_date = str(report.get("match_date") or "")
        if match_date:
            by_date[match_date] = _archive_item(report)
    by_date[str(current["match_date"])] = _archive_item(current)
    return [by_date[match_date] for match_date in sorted(by_date, reverse=True)]


def _archive_item(report: dict[str, Any]) -> dict[str, Any]:
    generation = report.get("editorial_generation")
    if not isinstance(generation, dict):
        generation = {}
    matches = report.get("matches")
    return {
        "match_date": str(report.get("match_date") or ""),
        "match_count": len(matches) if isinstance(matches, list) else 0,
        "generated_at": report.get("generated_at"),
        "compiled_at": report.get("compiled_at"),
        "scoring_version": report.get("scoring_version"),
        "uses_official_assists": bool(generation.get("uses_official_assists")),
        "uses_goal_involvements": bool(generation.get("uses_goal_involvements")),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _render_editorial_page(report: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Editor's Choices - {html.escape(report["match_date"], quote=False)}</title>
  <style>{_editorial_css()}</style>
</head>
<body>
  <main>
    <p class="eyebrow">FIFA PMSR Data</p>
    <h1>Editor's Choices · {html.escape(report["match_date"], quote=False)}</h1>
    <p class="lede">Data-informed selections from the latest structured PMSR dataset. These are not official awards.</p>
    {_choices_html(report["choices"])}
  </main>
</body>
</html>
"""


def _render_editorial_index(items: list[dict[str, Any]]) -> str:
    latest = items[0] if items else {}
    latest_date = html.escape(str(latest.get("match_date") or ""), quote=False)
    latest_line = (
        f'Latest available match-day editorial picks: <a href="{latest_date}/">{latest_date}</a>.'
        if latest_date
        else "No editorial reports have been published yet."
    )
    links = "\n".join(_archive_item_html(item) for item in items)
    if not links:
        links = '<p class="lede">Run the editorial workflow to publish the first report.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>Editor's Choices</title>
  <style>{_editorial_css()}</style>
</head>
<body>
  <main>
    <p class="eyebrow">FIFA PMSR Data</p>
    <h1>Editor's Choices</h1>
    <p class="lede">{latest_line}</p>
    <section class="archive-list" aria-label="Editorial archive">
      {links}
    </section>
  </main>
</body>
</html>
"""


def _archive_item_html(item: dict[str, Any]) -> str:
    match_date = html.escape(str(item["match_date"]), quote=False)
    badge_class = "badge official" if item["uses_official_assists"] else "badge legacy"
    badge_label = "official assists" if item["uses_official_assists"] else "legacy: no official assists"
    match_count = int(item.get("match_count") or 0)
    match_label = "match" if match_count == 1 else "matches"
    return (
        '<a class="archive-row" href="'
        f'{match_date}/">'
        f"<strong>{match_date}</strong>"
        f'<span>{match_count} {match_label}</span>'
        f'<span class="{badge_class}">{html.escape(badge_label, quote=False)}</span>'
        "</a>"
    )


def _choices_html(choices: list[dict[str, Any]]) -> str:
    cards = []
    for choice in choices:
        en = choice["content"]["en"]
        zh = choice["content"]["zh"]
        chips = "".join(
            f"<span>{html.escape(chip, quote=False)}</span>"
            for chip in choice["evidence_chips"]["en"]
        )
        badges = "".join(
            (
                '<span class="award-badge">'
                f'{html.escape(str(badge.get("label", {}).get("en") or ""), quote=False)}'
                "</span>"
            )
            for badge in choice.get("badges", [])
            if isinstance(badge, dict)
        )
        card = f"""
    <article class="choice-card">
      <div>
        <p class="award">{html.escape(choice["award_label"]["en"], quote=False)}</p>
        <div class="award-badges">{badges}</div>
        <h2>{html.escape(format_player(choice["player_name"], choice["team"]), quote=False)}</h2>
        <p class="meta">{html.escape(format_team(choice["team"]), quote=False)} vs {html.escape(format_team(choice["opponent"]), quote=False)} · Match {choice["match_no"]}</p>
        <h3>{html.escape(en["title"], quote=False)}</h3>
        {en["html"]}
        <h3>{html.escape(zh["title"], quote=False)}</h3>
        {zh["html"]}
      </div>
      <aside>
        <div class="chips">{chips}</div>
      </aside>
    </article>
        """
        cards.append("\n".join(line.rstrip() for line in card.strip("\n").splitlines()))
    return "\n".join(cards) if cards else "<p>No editorial choices generated.</p>"


def _editorial_css() -> str:
    return """
    :root { font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #17202a; background: #f5f7fb; }
    body { margin: 0; }
    main { max-width: 980px; margin: 0 auto; padding: 36px 20px 56px; }
    h1 { margin: 0 0 8px; font-size: 32px; }
    h2 { margin: 0 0 4px; font-size: 24px; }
    h3 { margin: 18px 0 6px; font-size: 16px; }
    p { line-height: 1.55; color: #435268; }
    .eyebrow, .award { color: #59677c; font-size: 12px; letter-spacing: 0; text-transform: uppercase; font-weight: 700; }
    .lede { margin-bottom: 24px; }
    .choice-card { display: grid; grid-template-columns: minmax(0, 1fr) 190px; gap: 18px; background: #fff; border: 1px solid #dde3ee; border-radius: 8px; padding: 22px; margin: 18px 0; }
    .choice-card aside { border-left: 1px solid #e8edf5; padding-left: 18px; }
    .choice-card aside strong { display: block; font-size: 34px; }
    .choice-card aside > span { color: #59677c; font-size: 12px; text-transform: uppercase; }
    .meta { margin: 0; color: #59677c; }
    .award-badges { display: flex; flex-wrap: wrap; gap: 6px; margin: -6px 0 10px; }
    .award-badge { border: 1px solid #dce5f2; background: #f7f9fc; color: #35465d; border-radius: 999px; padding: 4px 8px; font-size: 12px; font-weight: 700; }
    .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
    .chips span { background: #edf2fa; border: 1px solid #dce5f2; border-radius: 999px; padding: 5px 9px; font-size: 12px; }
    .archive-list { display: grid; gap: 10px; margin-top: 22px; }
    .archive-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 12px; padding: 14px 16px; color: inherit; text-decoration: none; background: #fff; border: 1px solid #dde3ee; border-radius: 8px; }
    .archive-row:hover { border-color: #b7c4d4; }
    .archive-row span { color: #59677c; font-size: 13px; }
    .badge { justify-self: end; border-radius: 999px; padding: 4px 9px; border: 1px solid #dce5f2; background: #edf2fa; color: #35465d; font-size: 12px; }
    .badge.official { border-color: #b7dfd4; background: #e7f7f1; color: #0f766e; }
    .badge.legacy { border-color: #e7d8ad; background: #fff7df; color: #806215; }
    @media (max-width: 720px) { .choice-card { grid-template-columns: 1fr; } .choice-card aside { border-left: 0; border-top: 1px solid #e8edf5; padding-left: 0; padding-top: 14px; } }
    @media (max-width: 720px) { .archive-row { grid-template-columns: 1fr; align-items: start; } .badge { justify-self: start; } }
    """
    pre_review = reports_path / f"{match_date}.pre-review.md"
    if pre_review.exists():
        pre_review.unlink()
