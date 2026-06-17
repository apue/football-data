import pytest

from football_data.discovery import parse_hub_sources, resolve_active_sources
from football_data.pipeline import PipelineError, build_update_events, validate_discovery_regression


BASE_URL = "https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php"


def _sources(html: str):
    return resolve_active_sources(
        parse_hub_sources(
            html,
            base_url=BASE_URL,
            discovered_at="2026-06-17T04:00:00+00:00",
        )
    )


def test_build_update_events_detects_new_matches_and_version_updates():
    previous = _sources(
        """
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M03-CAN-V-BIH.pdf">M03</a>
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M07-BRA-V-MAR.pdf">M07</a>
        """
    )
    current = _sources(
        """
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M03-CAN-V-BIH-V2.pdf">M03</a>
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M07-BRA-V-MAR.pdf">M07</a>
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M11-NED-V-JPN.pdf">M11</a>
        """
    )

    events = build_update_events(current, previous)

    assert events["new_matches"] == [
        {"match_no": 11, "source_id": "fifa-world-cup-2026-pmsr-m11-ned-jpn-v1"}
    ]
    assert events["version_updates"] == [
        {
            "match_no": 3,
            "from_version": 1,
            "to_version": 2,
            "source_id": "fifa-world-cup-2026-pmsr-m03-can-bih-v2",
        }
    ]


def test_validate_discovery_regression_blocks_unexpected_count_drop():
    current = _sources(
        '<a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M03-CAN-V-BIH.pdf">M03</a>'
    )
    previous = _sources(
        """
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M03-CAN-V-BIH.pdf">M03</a>
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M07-BRA-V-MAR.pdf">M07</a>
        """
    )

    with pytest.raises(PipelineError, match="discovery_regression"):
        validate_discovery_regression(current, previous)
