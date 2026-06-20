from __future__ import annotations

import json
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from football_data.database import build_database
from football_data.discovery import (
    DEFAULT_HUB_URL,
    DiscoveryError,
    discover_hub_sources,
    source_from_filename,
)
from football_data.extract import extract_pdf
from football_data.model import DiscoveredSource, ExtractedMatch


class PipelineError(RuntimeError):
    def __init__(self, failure_code: str, message: str) -> None:
        super().__init__(f"{failure_code}: {message}")
        self.failure_code = failure_code
        self.message = message


def pipeline_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_local_pdfs(raw_dir: str | Path) -> list[Path]:
    return sorted(Path(raw_dir).glob("**/*.pdf"))


def build_update_events(
    current_sources: list[DiscoveredSource],
    previous_sources: list[DiscoveredSource],
) -> dict[str, list[dict[str, object]]]:
    current_active = _active_by_match(current_sources)
    previous_active = _active_by_match(previous_sources)

    new_matches: list[dict[str, object]] = []
    version_updates: list[dict[str, object]] = []
    for key, current in sorted(current_active.items()):
        previous = previous_active.get(key)
        if previous is None:
            new_matches.append({"match_no": current.match_no, "source_id": current.source_id})
        elif current.version > previous.version:
            version_updates.append(
                {
                    "match_no": current.match_no,
                    "from_version": previous.version,
                    "to_version": current.version,
                    "source_id": current.source_id,
                }
            )
    return {"new_matches": new_matches, "version_updates": version_updates}


def validate_discovery_regression(
    current_sources: list[DiscoveredSource],
    previous_sources: list[DiscoveredSource],
) -> None:
    previous_active_count = len([source for source in previous_sources if source.active])
    current_active_count = len([source for source in current_sources if source.active])
    if previous_active_count and current_active_count < previous_active_count:
        raise PipelineError(
            "discovery_regression",
            f"FIFA hub active PMSR count dropped from {previous_active_count} to {current_active_count}",
        )


def ensure_source_pdfs(
    sources: list[DiscoveredSource],
    raw_dir: str | Path = "raw",
) -> tuple[dict[str, Path], list[str]]:
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    downloaded: list[str] = []
    for source in sources:
        destination = raw_path / source.competition / source.file_name
        if destination.exists():
            paths[source.source_id] = destination
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        _download(source.source_url, destination)
        paths[source.source_id] = destination
        downloaded.append(source.source_id)
    return paths, downloaded


def update_dataset(
    raw_dir: str | Path = "raw",
    db_path: str | Path = "data/latest.sqlite",
    manifests_dir: str | Path = "manifests",
    hub_url: str = DEFAULT_HUB_URL,
) -> list[ExtractedMatch]:
    generated_at = pipeline_timestamp()
    previous_sources = load_previous_sources(manifests_dir)
    discovered_sources: list[DiscoveredSource] = []
    events: dict[str, list[dict[str, object]]] = {
        "new_matches": [],
        "version_updates": [],
    }
    downloaded: list[str] = []
    failures: list[dict[str, object]] = []
    records: list[ExtractedMatch] = []

    try:
        discovered_sources = discover_hub_sources(hub_url, discovered_at=generated_at)
        validate_discovery_regression(discovered_sources, previous_sources)
        events = build_update_events(discovered_sources, previous_sources)
        active_sources = [source for source in discovered_sources if source.active]
        pdf_paths, downloaded = ensure_source_pdfs(active_sources, raw_dir)
        for source in active_sources:
            try:
                records.append(extract_pdf(pdf_paths[source.source_id], source))
            except Exception as exc:  # pragma: no cover - layout failures are fixture-driven later
                failures.append(
                    {
                        "failure_code": "pdf_parse_failed",
                        "source_id": source.source_id,
                        "source_url": source.source_url,
                        "message": str(exc),
                    }
                )
        if failures:
            raise PipelineError("pdf_parse_failed", f"{len(failures)} PDF parser failure(s)")
        if not records:
            raise PipelineError("sqlite_validation_failed", "No active PMSR records were parsed")
        build_database(db_path, records)
        write_manifests(
            records=records,
            discovered_sources=discovered_sources,
            events=events,
            downloaded=downloaded,
            failures=failures,
            manifests_dir=manifests_dir,
            generated_at=generated_at,
            status="success",
            failure_code=None,
            message="Dataset rebuilt from FIFA Match Report Hub active PMSR sources.",
        )
        return records
    except DiscoveryError as exc:
        write_manifests(
            records=records,
            discovered_sources=discovered_sources,
            events=events,
            downloaded=downloaded,
            failures=failures,
            manifests_dir=manifests_dir,
            generated_at=generated_at,
            status="failed",
            failure_code=exc.failure_code,
            message=str(exc),
        )
        raise PipelineError(exc.failure_code, str(exc)) from exc
    except PipelineError as exc:
        write_manifests(
            records=records,
            discovered_sources=discovered_sources,
            events=events,
            downloaded=downloaded,
            failures=failures,
            manifests_dir=manifests_dir,
            generated_at=generated_at,
            status="failed",
            failure_code=exc.failure_code,
            message=exc.message,
        )
        raise


def load_previous_sources(manifests_dir: str | Path) -> list[DiscoveredSource]:
    manifest_path = Path(manifests_dir)
    discovered_path = manifest_path / "discovered-sources.json"
    if discovered_path.exists():
        payload = json.loads(discovered_path.read_text(encoding="utf-8"))
        return [DiscoveredSource(**item) for item in payload.get("sources", [])]

    sources_path = manifest_path / "sources.json"
    if not sources_path.exists():
        return []
    payload = json.loads(sources_path.read_text(encoding="utf-8"))
    previous: list[DiscoveredSource] = []
    for item in payload.get("sources", []):
        source_payload = item.get("source", item)
        file_name = source_payload.get("file_name")
        if not file_name:
            continue
        source = source_from_filename(
            file_name,
            source_url=source_payload.get("source_url"),
            discovered_at=payload.get("generated_at"),
        )
        if source is not None:
            previous.append(source)
    return previous


def write_manifests(
    *,
    records: list[ExtractedMatch],
    discovered_sources: list[DiscoveredSource],
    events: dict[str, list[dict[str, object]]],
    downloaded: list[str],
    failures: list[dict[str, object]],
    manifests_dir: str | Path,
    generated_at: str,
    status: str,
    failure_code: str | None,
    message: str,
) -> None:
    manifest_path = Path(manifests_dir)
    manifest_path.mkdir(parents=True, exist_ok=True)
    sources = [
        {
            "match": asdict(record.match),
            "source": asdict(record.source),
        }
        for record in records
    ]
    (manifest_path / "sources.json").write_text(
        json.dumps({"generated_at": generated_at, "sources": sources}, indent=2) + "\n",
        encoding="utf-8",
    )
    (manifest_path / "discovered-sources.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "hub_url": DEFAULT_HUB_URL,
                "sources": [asdict(source) for source in discovered_sources],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (manifest_path / "update-events.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                **events,
                "downloaded": downloaded,
                "failures": failures,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    active_count = len([source for source in discovered_sources if source.active])
    (manifest_path / "latest-run.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": status,
                "failure_code": failure_code,
                "hub_url": DEFAULT_HUB_URL,
                "discovered": len(discovered_sources),
                "active_sources": active_count,
                "downloaded": len(downloaded),
                "parsed": len(records),
                "matches": len(records),
                "source_documents": len(records),
                **events,
                "failures": failures,
                "message": message,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _active_by_match(
    sources: list[DiscoveredSource],
) -> dict[tuple[str, str, int], DiscoveredSource]:
    return {
        (source.competition, source.report_type, source.match_no): source
        for source in sources
        if source.active
    }


def _download(source_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "fifa-pmsr-data/0.1 (+https://github.com/apue/football-data)",
            "Accept": "application/pdf,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = response.read()
    except Exception as exc:
        raise PipelineError("pdf_download_failed", f"{source_url}: {exc}") from exc
    destination.write_bytes(payload)
