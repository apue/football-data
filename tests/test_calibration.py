import json
import subprocess
import sys

from football_data.calibration import (
    build_potm_calibration_report,
    discover_potm_evidence_candidates,
)
from football_data.firecrawl import (
    build_firecrawl_url,
    extract_firecrawl_search_results,
    load_keypool_env,
)
from football_data.potm_evaluation import (
    evaluate_potm_workflow,
    render_potm_evaluation_markdown,
    score_evidence_result,
)


def test_keypool_env_and_firecrawl_search_result_parsing(tmp_path):
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "KEYPOOL_URL=keypool.example.test\nKEYPOOL_KEY='secret-token'\n",
        encoding="utf-8",
    )

    env = load_keypool_env(env_path)

    assert env["KEYPOOL_URL"] == "https://keypool.example.test"
    assert env["KEYPOOL_KEY"] == "secret-token"
    assert build_firecrawl_url(env["KEYPOOL_URL"], "/v2/search") == (
        "https://keypool.example.test/v2/search"
    )

    results = extract_firecrawl_search_results(
        {
            "success": True,
            "data": {
                "web": [
                    {
                        "title": "Caleb Yirenkyi scores stoppage-time winner",
                        "url": "https://example.com/caleb",
                        "description": "Ghana beat Panama 1-0.",
                    }
                ]
            },
        }
    )

    assert results == [
        {
            "title": "Caleb Yirenkyi scores stoppage-time winner",
            "url": "https://example.com/caleb",
            "description": "Ghana beat Panama 1-0.",
        }
    ]


def test_potm_calibration_report_flags_large_rank_misses(tmp_path):
    labels_path = tmp_path / "potm-labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "labels": [
                    {
                        "match_no": 21,
                        "match_key": "FIFA-2026-M21-GHA-PAN",
                        "potm_player_name": "Caleb YIRENKYI",
                        "source_url": "https://example.com/ghana-panama-potm",
                        "source_type": "manual",
                        "confidence": "confirmed",
                        "notes": "Stoppage-time winner.",
                    },
                    {
                        "match_no": 24,
                        "match_key": "FIFA-2026-M24-UZB-COL",
                        "potm_player_name": "Luis DIAZ",
                        "source_url": "https://example.com/uzbekistan-colombia-potm",
                        "source_type": "manual",
                        "confidence": "confirmed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_potm_calibration_report(
        db_path="data/latest.sqlite",
        labels_path=labels_path,
        match_date="2026-06-17",
        scoring_config_path="config/scoring/v0.1.json",
        top_n=3,
    )

    assert report["summary"]["label_count"] == 2
    assert report["summary"]["top3_hit_rate"] == 0.5

    caleb = next(item for item in report["items"] if item["potm_player_name"] == "Caleb YIRENKYI")
    assert caleb["model_rank"] == 7
    assert caleb["rank_diff"] == 6
    assert caleb["status"] == "red_flag"
    assert any("late" in signal for signal in caleb["possible_missing_signals"])

    diaz = next(item for item in report["items"] if item["potm_player_name"] == "Luis DIAZ")
    assert diaz["model_rank"] == 1
    assert diaz["status"] == "ok"


def test_calibrate_potm_cli_writes_markdown_report(tmp_path):
    labels_path = tmp_path / "potm-labels.json"
    report_path = tmp_path / "report.md"
    labels_path.write_text(
        json.dumps(
            {
                "labels": [
                    {
                        "match_no": 21,
                        "match_key": "FIFA-2026-M21-GHA-PAN",
                        "potm_player_name": "Caleb YIRENKYI",
                        "source_url": "https://example.com/ghana-panama-potm",
                        "confidence": "confirmed",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/calibrate_potm.py",
            "--date",
            "2026-06-17",
            "--labels",
            str(labels_path),
            "--out",
            str(report_path),
        ],
        check=True,
    )

    markdown = report_path.read_text(encoding="utf-8")
    assert "# POTM Calibration - 2026-06-17" in markdown
    assert "Caleb YIRENKYI" in markdown
    assert "Scoring version: `v0.2`" in markdown
    assert "rank 1" in markdown
    assert "ok" in markdown


def test_discover_potm_evidence_candidates_builds_queries_per_match():
    seen_queries: list[str] = []

    def fake_search(query: str, limit: int) -> list[dict[str, str]]:
        seen_queries.append(query)
        return [
            {
                "title": f"Result for {query}",
                "url": f"https://example.com/{len(seen_queries)}",
                "description": "Candidate evidence.",
            }
        ]

    report = discover_potm_evidence_candidates(
        db_path="data/latest.sqlite",
        match_date="2026-06-17",
        search_fn=fake_search,
        limit=2,
    )

    assert report["match_date"] == "2026-06-17"
    assert [match["match_no"] for match in report["matches"]] == [21, 22, 23, 24]
    assert report["matches"][0]["queries"][0].startswith("site:fifa.com")
    assert any("Ghana Panama" in query for query in report["matches"][0]["queries"])
    assert seen_queries == [
        query
        for match in report["matches"]
        for query in match["queries"]
    ]
    assert report["matches"][0]["results"][0]["query"] == report["matches"][0]["queries"][0]


def test_discover_potm_evidence_cli_dry_run_writes_queries(tmp_path):
    out_path = tmp_path / "candidates.json"

    subprocess.run(
        [
            sys.executable,
            "scripts/discover_potm_evidence.py",
            "--date",
            "2026-06-17",
            "--out",
            str(out_path),
            "--dry-run",
        ],
        check=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["match_date"] == "2026-06-17"
    assert payload["matches"][0]["match_key"] == "FIFA-2026-M21-GHA-PAN"
    assert payload["matches"][0]["results"] == []
    assert "Player of the Match" in payload["matches"][0]["queries"][0]


def test_potm_evaluation_scores_sources_and_flags_noise():
    evidence_report = {
        "match_date": "2026-06-17",
        "matches": [
            {
                "match_no": 21,
                "match_key": "FIFA-2026-M21-GHA-PAN",
                "home_team": "Ghana",
                "away_team": "Panama",
                "queries": [
                    'site:fifa.com "Player of the Match" "Ghana" "Panama"',
                    '"Ghana" "Panama" "Player of the Match"',
                ],
                "results": [
                    {
                        "query": 'site:fifa.com "Player of the Match" "Ghana" "Panama"',
                        "title": "FIFA Player of the Match: Caleb Yirenkyi",
                        "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/ghana-panama-potm",
                        "description": "Caleb Yirenkyi is named Player of the Match.",
                    },
                    {
                        "query": '"Ghana" "Panama" "Player of the Match"',
                        "title": "Ghana vs Panama highlights",
                        "url": "https://www.youtube.com/watch?v=example",
                        "description": "Full highlights and replay.",
                    },
                ],
            },
            {
                "match_no": 22,
                "match_key": "FIFA-2026-M22-ENG-CRO",
                "home_team": "England",
                "away_team": "Croatia",
                "queries": [
                    '"England" "Croatia" "Player of the Match"',
                ],
                "results": [
                    {
                        "query": '"England" "Croatia" "Player of the Match"',
                        "title": "England Croatia live reaction",
                        "url": "https://www.instagram.com/reel/example",
                        "description": "Fan reaction and interviews.",
                    }
                ],
            },
        ],
    }

    fifa_result = evidence_report["matches"][0]["results"][0]
    social_result = evidence_report["matches"][1]["results"][0]
    assert score_evidence_result(fifa_result)["source_tier"] == "official"
    assert score_evidence_result(fifa_result)["score"] > score_evidence_result(social_result)["score"]

    report = evaluate_potm_workflow(
        evidence_report=evidence_report,
        calibration_report={
            "summary": {"label_count": 1, "top3_hit_rate": 1.0},
            "items": [{"status": "ok"}],
        },
    )

    assert report["summary"]["match_count"] == 2
    assert report["dimensions"]["match_coverage"]["score"] == 1.0
    assert report["dimensions"]["potm_signal_coverage"]["score"] == 0.5
    assert report["dimensions"]["source_quality"]["score"] < 1.0
    assert report["dimensions"]["calibration_alignment"]["score"] == 1.0
    assert report["summary"]["status"] == "needs_more_evidence"
    assert any(finding["code"] == "high_noise_ratio" for finding in report["findings"])
    assert any(finding["code"] == "missing_potm_signal" for finding in report["findings"])

    markdown = render_potm_evaluation_markdown(report)
    assert "# POTM Workflow Evaluation - 2026-06-17" in markdown
    assert "high_noise_ratio" in markdown


def test_evaluate_potm_workflow_cli_writes_json_and_markdown(tmp_path):
    evidence_path = tmp_path / "evidence.json"
    json_out = tmp_path / "evaluation.json"
    md_out = tmp_path / "evaluation.md"
    evidence_path.write_text(
        json.dumps(
            {
                "match_date": "2026-06-17",
                "matches": [
                    {
                        "match_no": 21,
                        "match_key": "FIFA-2026-M21-GHA-PAN",
                        "home_team": "Ghana",
                        "away_team": "Panama",
                        "queries": ['site:fifa.com "Player of the Match" "Ghana" "Panama"'],
                        "results": [
                            {
                                "query": 'site:fifa.com "Player of the Match" "Ghana" "Panama"',
                                "title": "FIFA Player of the Match",
                                "url": "https://www.fifa.com/example",
                                "description": "Player of the Match award.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_potm_workflow.py",
            "--date",
            "2026-06-17",
            "--evidence",
            str(evidence_path),
            "--out",
            str(json_out),
            "--markdown-out",
            str(md_out),
        ],
        check=True,
    )

    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["match_date"] == "2026-06-17"
    assert payload["dimensions"]["source_quality"]["score"] == 1.0
    assert "POTM Workflow Evaluation" in md_out.read_text(encoding="utf-8")
