import json

import pytest

from football_data import pipeline as pipeline_module
from football_data.discovery import parse_hub_sources, resolve_active_sources
from football_data.model import DiscoveredSource
from football_data.pipeline import (
    PipelineError,
    build_update_events,
    ensure_source_pdfs,
    validate_discovery_regression,
)


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


def test_ensure_source_pdfs_ignores_legacy_root_cache(tmp_path, monkeypatch):
    source = DiscoveredSource(
        source_id="fifa-world-cup-2026-pmsr-m01-mex-rsa-v1",
        competition="fifa-world-cup-2026",
        report_type="pmsr",
        match_no=1,
        home_code="MEX",
        away_code="RSA",
        version=1,
        source_url="https://example.test/PMSR-M01%20MEX%20V%20RSA.pdf",
        file_name="PMSR-M01 MEX V RSA.pdf",
        discovered_at="2026-06-17T04:00:00+00:00",
    )
    legacy_path = tmp_path / source.file_name
    legacy_path.write_text("legacy root cache", encoding="utf-8")
    downloaded_paths = []

    def fake_download(source_url: str, destination):
        downloaded_paths.append(destination)
        destination.write_text(f"downloaded from {source_url}", encoding="utf-8")

    monkeypatch.setattr("football_data.pipeline._download", fake_download)

    paths, downloaded = ensure_source_pdfs([source], raw_dir=tmp_path)

    expected_path = tmp_path / source.competition / source.file_name
    assert paths[source.source_id] == expected_path
    assert downloaded == [source.source_id]
    assert downloaded_paths == [expected_path]
    assert expected_path.read_text(encoding="utf-8").startswith("downloaded")


def test_update_dataset_uses_default_stage_hubs(tmp_path, monkeypatch):
    captured_hub_urls = []

    def fake_discover_hub_sources(hub_urls, *, discovered_at):
        captured_hub_urls.append(tuple(hub_urls))
        return []

    monkeypatch.setattr(pipeline_module, "discover_hub_sources", fake_discover_hub_sources)

    with pytest.raises(PipelineError, match="No active PMSR"):
        pipeline_module.update_dataset(
            raw_dir=tmp_path / "raw",
            db_path=tmp_path / "latest.sqlite",
            manifests_dir=tmp_path / "manifests",
        )

    assert captured_hub_urls == [tuple(pipeline_module.DEFAULT_HUB_URLS)]
    latest_run = json.loads((tmp_path / "manifests" / "latest-run.json").read_text())
    discovered_sources = json.loads(
        (tmp_path / "manifests" / "discovered-sources.json").read_text()
    )
    assert latest_run["hub_urls"] == list(pipeline_module.DEFAULT_HUB_URLS)
    assert discovered_sources["hub_urls"] == list(pipeline_module.DEFAULT_HUB_URLS)
