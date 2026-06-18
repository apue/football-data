# Workflow

Use this sequence when asked to publish or check Editor's Choices.

1. Inspect repository state:

```bash
git status --short
python scripts/check_status.py
```

2. Refresh data if the user asks for the latest available match day:

```bash
python scripts/update_dataset.py
```

3. Find available local match dates:

```bash
sqlite3 data/latest.sqlite \
  "select match_date, count(*) from matches group by match_date order by match_date;"
```

4. Generate editorial artifacts. Omit `--date` for the latest available local match date:

```bash
python scripts/generate_editorial.py --date YYYY-MM-DD
```

Outputs:

- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `reports/editorial/YYYY-MM-DD.md`
- `site/index.html` is rebuilt by default so the homepage shows the latest cards.

5. Read the generated JSON and Markdown. Revise narratives only when the evidence supports the wording.

6. If you revise narratives by editing JSON or Markdown manually, rebuild the homepage:

```bash
python - <<'PY'
from football_data.demo import build_demo_site
build_demo_site("data/latest.sqlite", "site", "manifests")
PY
```

7. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

8. Follow `pr-policy.md` for publication.
