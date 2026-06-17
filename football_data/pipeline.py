from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from football_data.database import build_database
from football_data.extract import SOURCE_URLS, extract_pdf
from football_data.model import ExtractedMatch


def find_local_pdfs(raw_dir: str | Path) -> list[Path]:
    return sorted(Path(raw_dir).glob("*.pdf"))


def ensure_local_pdfs(raw_dir: str | Path = "raw") -> list[Path]:
    pdfs = find_local_pdfs(raw_dir)
    if pdfs:
        return pdfs
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)
    for file_name, source_url in SOURCE_URLS.items():
        destination = raw_path / file_name
        if destination.exists():
            continue
        _download(source_url, destination)
    return find_local_pdfs(raw_path)


def update_dataset(
    raw_dir: str | Path = "raw",
    db_path: str | Path = "data/latest.sqlite",
    manifests_dir: str | Path = "manifests",
) -> list[ExtractedMatch]:
    pdfs = ensure_local_pdfs(raw_dir)
    records = [extract_pdf(path) for path in pdfs]
    build_database(db_path, records)
    write_manifests(records, manifests_dir)
    return records


def write_manifests(records: list[ExtractedMatch], manifests_dir: str | Path) -> None:
    manifest_path = Path(manifests_dir)
    manifest_path.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
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
    (manifest_path / "latest-run.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "success",
                "matches": len(records),
                "source_documents": len(records),
                "message": "Dataset rebuilt from local raw PDF cache.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _download(source_url: str, destination: Path) -> None:
    request = urllib.request.Request(
        source_url,
        headers={
            "User-Agent": "fifa-pmsr-data/0.1 (+https://github.com/apue/football-data)",
            "Accept": "application/pdf,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    destination.write_bytes(payload)
