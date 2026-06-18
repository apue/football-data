# Narrative Style

Editor’s Choices are not dashboard prose. Write like a data-aware football editor.

Markdown is the human-readable source. Write and review copy in `reports/editorial/YYYY-MM-DD.md`; never make editorial wording changes directly in compiled frontend JSON.

## Principles

- Lead with the judgment, then give the reason.
- Use at most two or three hard numbers in each body paragraph.
- Put football actions before data labels: write what the player did on the pitch, then let evidence chips carry the audit trail.
- Translate metrics into football language:
  - `goals >= 3`: hat-trick / 帽子戏法
  - `line_breaks_completed` plus `ball_progressions`: breaking lines, carrying through pressure / 打穿防线、推进过压力区
  - `offers_received`, `in_between`, `in_behind`: finding pockets, receiving between lines / 在防线之间接应、身后接应
  - `possession_regains`, `possession_interrupted`: disrupting rhythm, winning the ball back / 打断节奏、夺回球权
- Do not pretend to have watched video. Avoid repeatedly naming the dataset in body copy; cite the evidence through chips and audit files.
- Do not list every metric. Keep detailed components in `evidence.json` for audit.
- Hidden Gem is optional. If the evidence is not strong, do not force one.

## English Tone

Use compact editorial language. Avoid hype unless the evidence is obvious.

Good:

> Messi did not leave much room for argument. The hat-trick decides the headline, and he was also involved in the moves that kept Argentina playing forward.

Bad:

> Messi had 3 goals, 6 shots, 4 shots on target, 16 receptions, 9 in-behind offers, and a score of 37.5.

## Chinese Tone

Use natural Chinese sports commentary. Write Chinese from evidence, not from the English draft. The Chinese copy should make the same editorial judgment, but it should not mirror English sentence order, metaphors, or abstractions.

Good:

> 姆巴佩这场一直压着塞内加尔后卫线踢。两个进球是结果，更持续的威胁来自他不断冲击身后空间。

Bad:

> 他给了这一天一个很直接的进攻答案。更有意思的是，他的跑动和接应一直在把防线往身后拉。

## Self-Check

Before publishing, check:

- Every claim is supported by `evidence.json` or SQLite.
- The English and Chinese versions make the same selection argument.
- The copy does not sound like a metric table.
- No external match observation is implied unless an external source was actually checked.
- After Markdown edits, run `scripts/render_editorial.py --date YYYY-MM-DD`.
