# Narrative Style

Editor’s Choices are not dashboard prose. Write like a data-aware football editor.

Markdown is the human-readable agent output. Review copy in `reports/editorial/YYYY-MM-DD.md`; never make editorial wording changes directly in compiled frontend JSON.

## Principles

- Lead with the judgment, then give the reason.
- Use at most two or three hard numbers in each body paragraph.
- Put football actions before data labels: write what the player did on the pitch, then let evidence chips carry the audit trail.
- Rewrite Chinese and English in separate passes from the same evidence.
- Do not use either finished language version as input for the other.
- Use `fact_bank.zh.json` as the Chinese input and `brief.en.json` as the English input.
- Vary the angle for each pick; do not reuse the same sentence frame across multiple players.
- Translate metrics into football language:
  - `goals >= 3`: hat-trick / 帽子戏法
  - `line_breaks_completed` plus `ball_progressions`: breaking lines, carrying through pressure / 打穿防线、推进过压力区
  - `offers_received`, `in_between`, `in_behind`: finding pockets, receiving between lines / 在防线之间接应、身后接应
  - `possession_regains`, `possession_interrupted`: disrupting rhythm, winning the ball back / 打断节奏、夺回球权
- Do not pretend to have watched video. Avoid repeatedly naming the dataset in body copy; cite the evidence through chips and audit files.
- Do not list every metric. Keep detailed components in `evidence.json` for audit.
- Hidden Gem is optional. If the evidence is not strong, do not force one.

## English Tone

Use compact editorial language. Avoid hype unless the evidence is obvious. Draft from `evidence.json`, not from the Chinese copy.

Good:

> Messi did not leave much room for argument. The hat-trick decides the headline, and he was also involved in the moves that kept Argentina playing forward.

Bad:

> Messi had 3 goals, 6 shots, 4 shots on target, 16 receptions, 9 in-behind offers, and a score of 37.5.

## Chinese Tone

Use natural Chinese sports commentary. Write Chinese from `fact_bank.zh.json`, not from the English draft and not from the generated Markdown frame. The Chinese copy should make the same editorial judgment, but it should not mirror English sentence order, metaphors, or abstractions.

Before writing each Chinese card, generate 3-5 Chinese title candidates from facts and allowed angles in `fact_bank.zh.json`. Pick the one that sounds most like a Chinese football post. Reject titles that feel mechanically abstract, such as `帽子戏法把答案写明了`; prefer direct phrasing such as `帽子戏法就是答案`.

After drafting Chinese, run a strict `qu-ai-wei` style review:

- Does it sound like a Chinese football editor wrote it directly?
- Is there at least one concrete football action before the numbers?
- Are abstract phrases and polished-but-empty claims removed?
- Is every claim supported by `fact_bank.zh.json`, `evidence.json`, or SQLite?

Use `humanizer-zh` style repair only for cards that fail this review. Repair rhythm and word choice, but do not change the player selection argument.

Good:

> 姆巴佩这场一直压着塞内加尔后卫线踢。两个进球是结果，更持续的威胁来自他不断冲击身后空间。

Bad:

> 他给了这一天一个很直接的进攻答案。更有意思的是，他的跑动和接应一直在把防线往身后拉。

## Self-Check

Before publishing, check:

- Every claim is supported by `evidence.json` or SQLite.
- The English and Chinese versions make the same selection argument.
- The copy does not sound like a metric table.
- Check the workflow gates: draft fact check, final editor, deterministic validation, and final fact-check warnings.
- Chinese final copy should read like a from-scratch Chinese sports editor wrote it after seeing the fact-check report.
- No external match observation is implied unless an external source was actually checked.
- If a card fails review, repair prompts/style packs or rerun `scripts/run_editorial_agent.py --date YYYY-MM-DD`.
