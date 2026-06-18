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

- `reports/editorial/YYYY-MM-DD.md`
- `site/editorial/YYYY-MM-DD/evidence.json`
- `site/editorial/YYYY-MM-DD/fact_bank.zh.json`
- `site/editorial/YYYY-MM-DD/brief.zh.json`
- `site/editorial/YYYY-MM-DD/brief.en.json`
- `site/editorial/latest.json`
- `site/editorial/YYYY-MM-DD/choices.json`
- `site/editorial/YYYY-MM-DD/index.html`
- `site/editorial/index.html`
- `site/index.html` is rebuilt by default so the homepage shows the latest cards.

Markdown is the human-readable source. `evidence.json` is the structured audit source. `fact_bank.zh.json` is the primary Chinese writing input. `brief.zh.json` is kept for compatibility and diagnostics; do not use it as the Chinese writing base. `brief.en.json` is the English writing input. `choices.json` is compiled frontend data with rendered HTML.

5. Read `site/editorial/YYYY-MM-DD/evidence.json`, `site/editorial/YYYY-MM-DD/fact_bank.zh.json`, `site/editorial/YYYY-MM-DD/brief.zh.json`, `site/editorial/YYYY-MM-DD/brief.en.json`, and `reports/editorial/YYYY-MM-DD.md`.

Treat generated Markdown as a draft brief, not publishable copy. It exists to carry the selected players, evidence chips, and top metrics into a human-editable shape.

Before rewriting copy, run the POTM calibration gate when labels exist or when Firecrawl can find credible match recognition for the date:

```bash
python scripts/calibrate_potm.py --date YYYY-MM-DD
```

If labels are missing, use the `calibrate-potm-labels` skill and `scripts/discover_potm_evidence.py --date YYYY-MM-DD` to find match-day candidate sources through Firecrawl/Keypool. Use `scripts/search_potm_evidence.py` only for targeted follow-up searches, then add only confirmed labels to `calibration/potm-labels.json`. POTM calibration is a sanity check: if the POTM is outside the model Top 3, pause and explain whether this is a known model gap, a one-off narrative choice, or a data extraction issue. Do not silently bend Editor's Choices around POTM.

Rewrite Chinese and English in separate passes from the same evidence. Use `fact_bank.zh.json` for Chinese and `brief.en.json` for English. Do not use either finished language version as input for the other. The two versions should make the same selection argument, but sentence order and idiom can differ.

For Chinese, act as a from-scratch Chinese sports editor: start from player, match, facts, and allowed angles in `fact_bank.zh.json`; do not inherit the draft Markdown sentence frame. Generate 3-5 Chinese title candidates from those facts, reject candidates that sound like translated English, and use the most natural one. Examples of natural title shape: `帽子戏法就是答案`, `最能把球带出去的人`, `不抢镜的连接器`.

Revise only the Markdown, and only when `evidence.json` or SQLite supports the wording.

6. Run an editorial review pass before rendering:

- First review Chinese with a strict `qu-ai-wei` style pass: plain Chinese, concrete football action, no empty polish, no factual drift.
- If a Chinese card still reads stiff or translated, repair that card with a `humanizer-zh` style pass without changing the selection argument.
- Does the Chinese read like a Chinese football post rather than an English rewrite?
- Does each card have a distinct football angle?
- Does obvious evidence stay direct while hidden-gem evidence gets a clear why-it-matters explanation?
- Are there at most two or three key numbers per body?
- Does the copy avoid implying video review or outside ratings?

If any card fails the editorial review pass, rewrite that card only.

7. If you revise Markdown, compile it back to frontend JSON/HTML:

```bash
python scripts/render_editorial.py --date YYYY-MM-DD
```

8. Verify:

```bash
python -m pytest -q
for f in examples/*.sql; do sqlite3 data/latest.sqlite < "$f" >/dev/null || exit 1; done
```

9. Follow `pr-policy.md` for publication.
