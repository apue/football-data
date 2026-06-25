#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from football_data.demo import build_demo_site
from football_data.editorial_artifacts import build_compiled_report, write_v2_artifacts
from football_data.editorial_copy_validation import validate_copy
from football_data.editorial_registry import load_copy_profile, load_editorial_experiment, load_review_profile
from football_data.editorial_review import build_editorial_review_payload, validate_editorial_review


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
    copy_profiles = {
        language: load_copy_profile(str(profile_id), args.config_dir)
        for language, profile_id in (experiment.get("copy_profiles") or {}).items()
    }
    copy_validation = validate_copy(copy, copy_profiles, copy_payload=copy_payload)
    if copy_validation["status"] != "pass":
        raise RuntimeError(f"Editorial v2 copy validation failed: {copy_validation['warnings']}")
    editorial_review_payload = None
    editorial_review = None
    editorial_review_validation = None
    review_profile_id = experiment.get("review_profile")
    if review_profile_id:
        review_profile = load_review_profile(str(review_profile_id), args.config_dir)
        editorial_review_payload = build_editorial_review_payload(
            selection_decision=selection_decision,
            candidate_pool=candidate_pool,
            copy=copy,
            selection_validation=selection_validation,
            copy_validation=copy_validation,
            review_profile=review_profile,
            selection_config=experiment.get("selection"),
        )
        editorial_review = _load_json(audit_dir / "editorial_review.json")
        editorial_review_validation = validate_editorial_review(
            editorial_review,
            review_profile,
            editorial_review_payload,
        )
        if editorial_review_validation["status"] != "pass":
            raise RuntimeError(f"Editorial v2 review validation failed: {editorial_review_validation['warnings']}")
    compiled = build_compiled_report(
        experiment=experiment,
        rankings=rankings,
        candidate_pool=candidate_pool,
        selection_decision=selection_decision,
        selection_validation=selection_validation,
        copy=copy,
        editorial_review_validation=editorial_review_validation,
    )
    run_payload = {
        **previous_run,
        "status": "success",
        "copy_validation": copy_validation,
        "editorial_review_validation": editorial_review_validation,
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
        editorial_review_payload=editorial_review_payload,
        editorial_review=editorial_review,
        editorial_review_validation=editorial_review_validation,
        run_payload=run_payload,
        copy_validation=copy_validation,
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
