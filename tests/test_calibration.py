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
    assert "rank 7" in markdown
    assert "red_flag" in markdown


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
    assert "Ghana Panama" in report["matches"][0]["queries"][0]
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
