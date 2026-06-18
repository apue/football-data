from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


EVALUATION_WEIGHTS = {
    "match_coverage": 0.20,
    "source_quality": 0.25,
    "potm_signal_coverage": 0.25,
    "noise_ratio": 0.15,
    "query_quality": 0.10,
    "calibration_alignment": 0.25,
}

OFFICIAL_DOMAINS = ("fifa.com", "fifatrainingcentre.com")
NEWS_DOMAINS = (
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "espn.com",
    "espn.co.uk",
    "nytimes.com",
    "reuters.com",
    "theathletic.com",
    "theguardian.com",
)
SPORTS_DOMAINS = (
    "foxsports.com",
    "goal.com",
    "skysports.com",
)
VIDEO_DOMAINS = ("youtube.com", "youtu.be", "dailymotion.com", "twitch.tv")
SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "reddit.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
)
POTM_TERMS = ("player of the match", "potm")
NOISE_TERMS = (
    "full highlights",
    "highlight",
    "interview",
    "live",
    "reaction",
    "replay",
    "watch",
)


def evaluate_potm_workflow(
    *,
    evidence_report: dict[str, Any],
    calibration_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matches = evidence_report.get("matches", [])
    evaluated_matches = [_evaluate_match(match) for match in matches]
    calibration_summary = (calibration_report or {}).get("summary", {})
    label_count = int(calibration_summary.get("label_count") or 0)

    dimensions = _dimensions(
        evaluated_matches=evaluated_matches,
        calibration_summary=calibration_summary,
        label_count=label_count,
    )
    overall_score = _overall_score(dimensions)
    findings = _findings(evaluated_matches, dimensions, label_count=label_count)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "match_date": evidence_report.get("match_date"),
        "summary": {
            "match_count": len(evaluated_matches),
            "result_count": sum(match["result_count"] for match in evaluated_matches),
            "label_count": label_count,
            "overall_score": overall_score,
            "status": _status(overall_score, dimensions),
        },
        "dimensions": dimensions,
        "findings": findings,
        "matches": evaluated_matches,
    }


def score_evidence_result(result: dict[str, Any]) -> dict[str, Any]:
    domain = _domain(result.get("url", ""))
    source_tier, base_score = _source_tier(domain)
    content_text = " ".join(
        str(result.get(key) or "")
        for key in ("title", "description", "url")
    ).lower()
    potm_signal = any(term in content_text for term in POTM_TERMS)
    noise_signal = any(term in content_text for term in NOISE_TERMS) or source_tier in {"video", "social"}
    score = base_score
    if potm_signal:
        score += 0.20
    if noise_signal:
        score -= 0.20
    score = max(0.0, min(1.0, score))
    return {
        "title": str(result.get("title") or ""),
        "url": str(result.get("url") or ""),
        "domain": domain,
        "source_tier": source_tier,
        "score": round(score, 4),
        "potm_signal": potm_signal,
        "noise_signal": noise_signal,
    }


def render_potm_evaluation_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# POTM Workflow Evaluation - {report['match_date']}",
        "",
        f"- Overall score: {report['summary']['overall_score']:.2f}",
        f"- Status: `{report['summary']['status']}`",
        f"- Matches: {report['summary']['match_count']}",
        f"- Candidate results: {report['summary']['result_count']}",
        f"- POTM labels: {report['summary']['label_count']}",
        "",
        "## Dimensions",
        "",
    ]
    for name, dimension in report["dimensions"].items():
        value = dimension.get("value")
        value_text = "n/a" if value is None else f"{value:.2f}"
        score = dimension.get("score")
        score_text = "n/a" if score is None else f"{score:.2f}"
        lines.append(f"- `{name}`: value {value_text}, score {score_text}")

    lines.extend(["", "## Findings", ""])
    if report["findings"]:
        for finding in report["findings"]:
            match_no = finding.get("match_no")
            prefix = f"Match {match_no}: " if match_no else ""
            lines.append(f"- `{finding['code']}`: {prefix}{finding['message']}")
    else:
        lines.append("- No blocking findings.")

    lines.extend(["", "## Matches", ""])
    for match in report["matches"]:
        best = match.get("best_result")
        best_text = (
            f"{best['source_tier']} {best['score']:.2f} - {best['title']}"
            if best
            else "no results"
        )
        lines.append(
            f"- M{match['match_no']} {match['home_team']} v {match['away_team']}: {best_text}"
        )
    return "\n".join(lines).rstrip() + "\n"


def _evaluate_match(match: dict[str, Any]) -> dict[str, Any]:
    scored_results = [score_evidence_result(result) for result in match.get("results", [])]
    best_result = max(scored_results, key=lambda result: result["score"], default=None)
    return {
        "match_no": match.get("match_no"),
        "match_key": match.get("match_key"),
        "home_team": match.get("home_team"),
        "away_team": match.get("away_team"),
        "query_count": len(match.get("queries", [])),
        "result_count": len(scored_results),
        "has_results": bool(scored_results),
        "has_official_query": any("site:fifa.com" in query for query in match.get("queries", [])),
        "has_exact_potm_query": any("Player of the Match" in query for query in match.get("queries", [])),
        "has_potm_signal": any(result["potm_signal"] for result in scored_results),
        "noise_count": sum(1 for result in scored_results if result["noise_signal"]),
        "best_result": best_result,
        "results": scored_results,
    }


def _dimensions(
    *,
    evaluated_matches: list[dict[str, Any]],
    calibration_summary: dict[str, Any],
    label_count: int,
) -> dict[str, dict[str, float | None]]:
    match_count = len(evaluated_matches)
    result_count = sum(match["result_count"] for match in evaluated_matches)
    noise_count = sum(match["noise_count"] for match in evaluated_matches)
    best_scores = [
        match["best_result"]["score"] if match["best_result"] else 0.0
        for match in evaluated_matches
    ]
    noise_ratio = noise_count / result_count if result_count else 1.0
    dimensions: dict[str, dict[str, float | None]] = {
        "match_coverage": _dimension(
            sum(1 for match in evaluated_matches if match["has_results"]) / match_count
            if match_count
            else 0.0
        ),
        "source_quality": _dimension(
            sum(best_scores) / len(best_scores) if best_scores else 0.0
        ),
        "potm_signal_coverage": _dimension(
            sum(1 for match in evaluated_matches if match["has_potm_signal"]) / match_count
            if match_count
            else 0.0
        ),
        "noise_ratio": {"value": round(noise_ratio, 4), "score": round(1.0 - noise_ratio, 4)},
        "query_quality": _dimension(
            sum(
                1
                for match in evaluated_matches
                if match["has_official_query"] and match["has_exact_potm_query"]
            )
            / match_count
            if match_count
            else 0.0
        ),
        "calibration_alignment": {
            "value": (
                round(float(calibration_summary.get("top3_hit_rate") or 0.0), 4)
                if label_count
                else None
            ),
            "score": (
                round(float(calibration_summary.get("top3_hit_rate") or 0.0), 4)
                if label_count
                else None
            ),
        },
    }
    return dimensions


def _dimension(value: float) -> dict[str, float]:
    rounded = round(max(0.0, min(1.0, value)), 4)
    return {"value": rounded, "score": rounded}


def _overall_score(dimensions: dict[str, dict[str, float | None]]) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for name, dimension in dimensions.items():
        score = dimension.get("score")
        if score is None:
            continue
        weight = EVALUATION_WEIGHTS[name]
        weighted_sum += float(score) * weight
        weight_sum += weight
    return round(weighted_sum / weight_sum, 4) if weight_sum else 0.0


def _findings(
    evaluated_matches: list[dict[str, Any]],
    dimensions: dict[str, dict[str, float | None]],
    *,
    label_count: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if dimensions["noise_ratio"]["value"] is not None and dimensions["noise_ratio"]["value"] >= 0.5:
        findings.append(
            {
                "code": "high_noise_ratio",
                "severity": "warning",
                "message": "At least half of candidate results are video, social, replay, live, or highlights noise.",
            }
        )
    if label_count == 0:
        findings.append(
            {
                "code": "missing_labels",
                "severity": "info",
                "message": "No confirmed POTM labels were available, so model alignment was not scored.",
            }
        )
    for match in evaluated_matches:
        if not match["has_results"]:
            findings.append(
                {
                    "code": "missing_candidates",
                    "severity": "error",
                    "match_no": match["match_no"],
                    "message": "No external evidence candidates were found.",
                }
            )
        elif not match["has_potm_signal"]:
            findings.append(
                {
                    "code": "missing_potm_signal",
                    "severity": "warning",
                    "match_no": match["match_no"],
                    "message": "Candidates exist, but none clearly mention Player of the Match or POTM.",
                }
            )
        if match["best_result"] and match["best_result"]["score"] < 0.5:
            findings.append(
                {
                    "code": "weak_best_source",
                    "severity": "warning",
                    "match_no": match["match_no"],
                    "message": "The best candidate source is still weak for label confirmation.",
                }
            )
    return findings


def _status(overall_score: float, dimensions: dict[str, dict[str, float | None]]) -> str:
    if dimensions["noise_ratio"]["value"] is not None and dimensions["noise_ratio"]["value"] >= 0.5:
        return "needs_more_evidence"
    if overall_score >= 0.75:
        return "ready_for_review"
    if overall_score >= 0.55:
        return "needs_more_evidence"
    return "weak"


def _source_tier(domain: str) -> tuple[str, float]:
    if _matches_domain(domain, OFFICIAL_DOMAINS):
        return "official", 0.85
    if _matches_domain(domain, NEWS_DOMAINS):
        return "news", 0.65
    if _matches_domain(domain, SPORTS_DOMAINS):
        return "sports", 0.60
    if _matches_domain(domain, VIDEO_DOMAINS):
        return "video", 0.30
    if _matches_domain(domain, SOCIAL_DOMAINS):
        return "social", 0.20
    return "unknown", 0.40


def _matches_domain(domain: str, suffixes: tuple[str, ...]) -> bool:
    return any(domain == suffix or domain.endswith("." + suffix) for suffix in suffixes)


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")
