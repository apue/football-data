from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from html.parser import HTMLParser

from football_data.model import DiscoveredSource


DEFAULT_HUB_URL = (
    "https://www.fifatrainingcentre.com/en/fifa-world-cup-2026/match-report-hub.php"
)
DEFAULT_COMPETITION = "fifa-world-cup-2026"
REPORT_TYPE = "PMSR"
USER_AGENT = "fifa-pmsr-data/0.1 (+https://github.com/apue/football-data)"


class DiscoveryError(RuntimeError):
    def __init__(self, failure_code: str, message: str) -> None:
        super().__init__(message)
        self.failure_code = failure_code


def discovery_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_hub_html(hub_url: str = DEFAULT_HUB_URL) -> str:
    request = urllib.request.Request(
        hub_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - exercised in integration/CI
        raise DiscoveryError("hub_fetch_failed", f"Could not fetch FIFA hub: {exc}") from exc


def discover_hub_sources(
    hub_url: str = DEFAULT_HUB_URL,
    *,
    discovered_at: str | None = None,
) -> list[DiscoveredSource]:
    html = fetch_hub_html(hub_url)
    sources = parse_hub_sources(
        html,
        base_url=hub_url,
        discovered_at=discovered_at or discovery_timestamp(),
    )
    if not sources:
        raise DiscoveryError("hub_parse_failed", "No PMSR PDF links found on FIFA hub")
    return resolve_active_sources(sources)


def parse_hub_sources(
    html: str,
    *,
    base_url: str,
    discovered_at: str,
    competition: str = DEFAULT_COMPETITION,
) -> list[DiscoveredSource]:
    parser = _HrefParser()
    parser.feed(html)
    sources: list[DiscoveredSource] = []
    seen: set[str] = set()
    for href in parser.hrefs:
        if "PMSR" not in href.upper() or ".PDF" not in href.upper():
            continue
        source_url = _normalise_url(base_url, href)
        if source_url in seen:
            continue
        seen.add(source_url)
        file_name = _file_name_from_url(source_url)
        source = source_from_filename(
            file_name,
            source_url=source_url,
            discovered_at=discovered_at,
            competition=competition,
        )
        if source is not None:
            sources.append(source)
    return sorted(sources, key=lambda source: (source.match_no, source.version, source.source_url))


def resolve_active_sources(sources: list[DiscoveredSource]) -> list[DiscoveredSource]:
    active_by_match: dict[tuple[str, str, int], DiscoveredSource] = {}
    for source in sources:
        key = (source.competition, source.report_type, source.match_no)
        current = active_by_match.get(key)
        if current is None or (source.version, source.source_url) > (
            current.version,
            current.source_url,
        ):
            active_by_match[key] = source

    resolved: list[DiscoveredSource] = []
    for source in sources:
        key = (source.competition, source.report_type, source.match_no)
        is_active = source == active_by_match[key]
        resolved.append(
            replace(source, active=is_active, status="active" if is_active else "superseded")
        )
    return resolved


def source_from_filename(
    file_name: str,
    *,
    source_url: str | None,
    discovered_at: str | None,
    competition: str = DEFAULT_COMPETITION,
) -> DiscoveredSource | None:
    decoded = urllib.parse.unquote(file_name)
    stem = decoded[:-4] if decoded.lower().endswith(".pdf") else decoded
    match = re.search(
        r"PMSR[-\s]*M(?P<match_no>\d{1,3})[-\s]+"
        r"(?P<home>[A-Z]{2,3})[-\s]+V[-\s]+(?P<away>[A-Z]{2,3})(?P<tail>.*)$",
        stem,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    match_no = int(match.group("match_no"))
    home_code = match.group("home").upper()
    away_code = match.group("away").upper()
    version = _parse_version(match.group("tail"))
    source_id = (
        f"{competition}-pmsr-m{match_no:02d}-{home_code.lower()}-"
        f"{away_code.lower()}-v{version}"
    )
    return DiscoveredSource(
        source_id=source_id,
        competition=competition,
        report_type=REPORT_TYPE,
        match_no=match_no,
        home_code=home_code,
        away_code=away_code,
        version=version,
        source_url=source_url or "",
        file_name=decoded,
        discovered_at=discovered_at or discovery_timestamp(),
    )


def _parse_version(tail: str) -> int:
    versions = [int(value) for value in re.findall(r"(?:^|[-_\s])V(\d+)(?=$|[-_\s.])", tail.upper())]
    return max(versions) if versions else 1


def _normalise_url(base_url: str, href: str) -> str:
    joined = urllib.parse.urljoin(base_url, href.strip())
    parts = urllib.parse.urlsplit(joined)
    path = urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/-._~")
    query = urllib.parse.quote(urllib.parse.unquote(parts.query), safe="=&?-._~")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def _file_name_from_url(source_url: str) -> str:
    path = urllib.parse.urlsplit(source_url).path
    return urllib.parse.unquote(path.rsplit("/", 1)[-1])


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_by_name = {name.lower(): value for name, value in attrs}
        href = attrs_by_name.get("href")
        if href:
            self.hrefs.append(href)
