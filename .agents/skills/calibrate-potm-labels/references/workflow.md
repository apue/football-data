# POTM Calibration Workflow

Use this when Codex needs to find external match recognition, compare it with our model ranks, and decide whether scoring weights need review.

## Inputs

- SQLite database: `data/latest.sqlite`
- Scoring config: `config/scoring/v0.1.json`
- Label store: `calibration/potm-labels.json`
- Report output: `calibration/reports/YYYY-MM-DD.md`
- Firecrawl search through Keypool env: `.env.local` with `KEYPOOL_URL` and `KEYPOOL_KEY`

## Evidence Discovery

Run match-day discovery first. Use `--dry-run` when you only want to inspect generated queries:

```bash
python scripts/discover_potm_evidence.py --date YYYY-MM-DD --dry-run
python scripts/discover_potm_evidence.py --date YYYY-MM-DD
```

The output goes to `calibration/evidence/YYYY-MM-DD.json`. Review those candidates before writing labels.

Use targeted search for gaps or ambiguous matches:

```bash
python scripts/search_potm_evidence.py "FIFA 2026 Match 21 Ghana Panama Player of the Match" --limit 5
python scripts/search_potm_evidence.py "Ghana Panama Caleb Yirenkyi player of the match FIFA" --limit 5 --json
```

Use Firecrawl results as candidate evidence. Prefer official FIFA pages first, then reputable match reports. Do not add a label from vague social chatter alone.

## Label Format

Add confirmed labels to `calibration/potm-labels.json`:

```json
{
  "labels": [
    {
      "match_date": "2026-06-17",
      "match_no": 21,
      "match_key": "FIFA-2026-M21-GHA-PAN",
      "potm_player_name": "Caleb YIRENKYI",
      "source_url": "https://example.com/source",
      "source_type": "fifa|news|manual",
      "confidence": "confirmed|probable",
      "notes": "Stoppage-time winner."
    }
  ]
}
```

Keep names aligned with `player_match_stats.player_name` where possible.

## Run Calibration

```bash
python scripts/calibrate_potm.py --date YYYY-MM-DD
python scripts/calibrate_potm.py --date YYYY-MM-DD --json
```

The report compares each POTM with same-match model ranking:

- `model_rank`: where the POTM appears in our per-match model list.
- `rank_diff`: `model_rank - 1`; larger values mean stronger disagreement.
- `top3_hit_rate`: share of labels that landed in the model Top 3.
- `status`: `ok`, `warning`, `red_flag`, or `missing`.

## Interpretation

POTM is a weak label. Do not use POTM as a scoring input.

Use rank misses as review prompts:

- Late winner outside Top 3: inspect impact/game-state weights.
- Goal plus assist outside Top 3: inspect goal involvement and deciding-action weights.
- Defender or goalkeeper outside Top 3: inspect defensive and keeper action coverage.
- Missing player: inspect extraction/name matching before discussing weights.

Do not change production weights from one red flag. Propose a temporary scoring config only after several reports show the same pattern.
