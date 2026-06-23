#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from football_data.demo import build_demo_site
from football_data.editorial_artifacts import build_compiled_report, write_v2_artifacts
from football_data.editorial_registry import load_editorial_experiment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompile Editorial v2 public artifacts from existing audit files."
    )
    parser.add_argument("--date", required=True, help="Match date to recompile.")
    parser.add_argument("--db", default="data/latest.sqlite", help="SQLite database path.")
    parser.add_argument("--site-dir", default="site", help="Site output directory.")
    parser.add_argument("--reports-dir", default="reports", help="Reports output directory.")
    parser.add_argument("--manifests-dir", default="manifests", help="Manifests directory.")
    parser.add_argument("--agent-runs-dir", default="agent-runs", help="Agent audit directory.")
    parser.add_argument("--config-dir", default="config/editorial", help="Editorial registry directory.")
    parser.add_argument("--out", default="manifests/editorial-v2-run.json", help="Run manifest output.")
    parser.add_argument("--no-homepage", action="store_true", help="Do not rebuild homepage.")
    parser.add_argument("--json", action="store_true", help="Print run JSON.")
    args = parser.parse_args()

    audit_dir = Path(args.agent_runs_dir) / args.date
    rankings = _load_json(audit_dir / "rankings.json")
    candidate_pool = _load_json(audit_dir / "candidate_pool.json")
    selector_input = _load_json(audit_dir / "selector_input.json")
    selection_decision = _load_json(audit_dir / "selection_decision.json")
    selection_validation = _load_json(audit_dir / "selection_validation.json")
    copy_payload = _load_json(audit_dir / "copy_payload.json")
    copy = _load_json(audit_dir / "copy.json")
    previous_run = _load_json(audit_dir / "run.json")

    experiment = load_editorial_experiment(previous_run.get("experiment_id"), args.config_dir)
    compiled = build_compiled_report(
        experiment=experiment,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy=copy,
    )
    run_payload = {
        **previous_run,
        "status": "success",
        "recompiled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    write_v2_artifacts(
        compiled=compiled,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selector_input=selector_input,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy_payload=copy_payload,
        copy=copy,
        run_payload=run_payload,
        site_dir=args.site_dir,
        reports_dir=args.reports_dir,
        agent_runs_dir=args.agent_runs_dir,
        run_out_path=args.out,
    )
    if not args.no_homepage:
        build_demo_site(args.db, args.site_dir, args.manifests_dir)
    if args.json:
        print(json.dumps(run_payload, ensure_ascii=False, indent=2))
    else:
        print(f"Recompiled Editorial v2 artifacts for {args.date}")
    return 0


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing audit file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Audit file must contain a JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
