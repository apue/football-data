from football_data import discovery
from football_data.discovery import parse_hub_sources, resolve_active_sources


def test_parse_hub_sources_handles_spaces_and_version_suffixes():
    html = """
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M01 MEX V RSA.pdf">M01</a>
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M03-CAN-V-BIH-V2.pdf">M03</a>
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M07-BRA-V-MAR POST-V2.pdf">M07</a>
    """

    sources = parse_hub_sources(
        html,
        base_url="https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php",
        discovered_at="2026-06-17T04:00:00+00:00",
    )

    assert [source.match_no for source in sources] == [1, 3, 7]
    assert [(source.home_code, source.away_code) for source in sources] == [
        ("MEX", "RSA"),
        ("CAN", "BIH"),
        ("BRA", "MAR"),
    ]
    assert [source.version for source in sources] == [1, 2, 2]
    assert sources[0].file_name == "PMSR-M01 MEX V RSA.pdf"
    assert sources[0].source_url.endswith("PMSR-M01%20MEX%20V%20RSA.pdf")
    assert sources[2].source_id == "fifa-world-cup-2026-pmsr-m07-bra-mar-v2"


def test_resolve_active_sources_marks_highest_version_active():
    html = """
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M10-GER-V-CUW.pdf">M10 V1</a>
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M10-GER-V-CUW-V2.pdf">M10 V2</a>
    <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M11-NED-V-JPN.pdf">M11</a>
    """
    sources = parse_hub_sources(
        html,
        base_url="https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php",
        discovered_at="2026-06-17T04:00:00+00:00",
    )

    resolved = resolve_active_sources(sources)

    assert [(source.match_no, source.version, source.active) for source in resolved] == [
        (10, 1, False),
        (10, 2, True),
        (11, 1, True),
    ]
    assert [source.source_id for source in resolved if source.active] == [
        "fifa-world-cup-2026-pmsr-m10-ger-cuw-v2",
        "fifa-world-cup-2026-pmsr-m11-ned-jpn-v1",
    ]


def test_discover_hub_sources_combines_default_stage_hubs(monkeypatch):
    html_by_url = {
        "https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php": """
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M01-MEX-V-RSA.pdf">M01</a>
        """,
        "https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub-knockout-stage.php": """
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M73-RSA-V-CAN.pdf">M73</a>
        <a href="/media/native/tournaments/fifa-world-cup/2026/PMSR-M01-MEX-V-RSA.pdf">M01 duplicate</a>
        """,
    }
    fetched_urls = []

    def fake_fetch_hub_html(hub_url: str) -> str:
        fetched_urls.append(hub_url)
        return html_by_url[hub_url]

    monkeypatch.setattr(discovery, "fetch_hub_html", fake_fetch_hub_html)

    sources = discovery.discover_hub_sources(
        discovery.DEFAULT_HUB_URLS,
        discovered_at="2026-06-30T00:00:00+00:00",
    )

    assert fetched_urls == list(discovery.DEFAULT_HUB_URLS)
    assert [source.match_no for source in sources] == [1, 73]
    assert [source.source_id for source in sources] == [
        "fifa-world-cup-2026-pmsr-m01-mex-rsa-v1",
        "fifa-world-cup-2026-pmsr-m73-rsa-can-v1",
    ]
