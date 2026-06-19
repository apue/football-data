from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_SCORING_CONFIG = "config/scoring/v0.3.json"


def editorial_input_fingerprint(
    db_path: str | Path,
    match_date: str,
    scoring_config_path: str | Path = DEFAULT_SCORING_CONFIG,
) -> dict[str, Any]:
    scoring_path = Path(scoring_config_path)
    scoring_text = scoring_path.read_text(encoding="utf-8")
    scoring = json.loads(scoring_text)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        schema_version = _meta_value(conn, "schema_version")
        matches = [
            dict(row)
            for row in conn.execute(
                """
                select match_key, source_id, match_no, match_date,
                       home_team, away_team, home_score, away_score
                from matches
                where match_date = ?
                order by match_no
                """,
                (match_date,),
            )
        ]
        source_documents = [
            dict(row)
            for row in conn.execute(
                """
                select s.source_id, s.match_key, s.match_no, s.version,
                       s.sha256, s.file_size, s.source_url
                from source_documents s
                join matches m on m.match_key = s.match_key
                where m.match_date = ? and s.active = 1
                order by s.match_no, s.version, s.source_id
                """,
                (match_date,),
            )
        ]
    finally:
        conn.close()

    payload = {
        "schema_version": schema_version,
        "match_date": match_date,
        "scoring_version": scoring.get("version"),
        "scoring_config_sha256": hashlib.sha256(scoring_text.encode("utf-8")).hexdigest(),
        "matches": matches,
        "source_documents": source_documents,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        **payload,
        "input_hash": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _meta_value(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("select value from meta where key = ?", (key,)).fetchone()
    return str(row[0]) if row and row[0] is not None else None
