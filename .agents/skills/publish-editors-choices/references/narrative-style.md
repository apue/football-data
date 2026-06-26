# Narrative Style

Editor’s Choices are not dashboard prose. Write like a data-aware football editor.

Markdown is the human-readable agent output. Review copy in `reports/editorial/YYYY-MM-DD.md`; never make editorial wording changes directly in compiled frontend JSON.

## Principles

- Lead with the judgment, then give the reason.
- Use at most two or three hard numbers in each body paragraph.
- Put football actions before data labels: write what the player did on the pitch, then let evidence chips carry the audit trail.
- Write Chinese and English from the same selected candidate evidence packet.
- Do not use either finished language version as input for the other.
- Vary the angle for each pick; do not reuse the same sentence frame across multiple players.
- Translate metrics into football language:
  - `goals >= 3`: hat-trick / 帽子戏法
  - `line_breaks_completed` plus `ball_progressions`: breaking lines, carrying through pressure / 打穿防线、推进过压力区
  - `offers_received`, `in_between`, `in_behind`: finding pockets, receiving between lines / 在防线之间接应、身后接应
  - `possession_regains`, `possession_interrupted`: disrupting rhythm, winning the ball back / 打断节奏、夺回球权
- Do not pretend to have watched video. Avoid repeatedly naming the dataset in body copy; cite the evidence through chips and audit files.
- Do not list every metric. Keep detailed components in `agent-runs/YYYY-MM-DD/candidate_pool.json` for audit.
- Avoid negated contrast claims such as "not only..." or `不是只在...`; if the data only shows additional actions, state those actions directly.
- Hidden Gem is optional. If the evidence is not strong, do not force one.

## English Tone

Use compact editorial language. Avoid hype unless the evidence is obvious. Draft from the selected candidate evidence packet, not from the Chinese copy.

Good:

> Messi did not leave much room for argument. The hat-trick decides the headline, and he was also involved in the moves that kept Argentina playing forward.

Bad:

> Messi had 3 goals, 6 shots, 4 shots on target, 16 receptions, 9 in-behind offers, and a score of 37.5.

## Chinese Tone

Use natural Chinese sports commentary. Write Chinese from the selected candidate evidence packet, not from the English draft and not from the generated Markdown frame. The Chinese copy should make the same editorial judgment, but it should not mirror English sentence order, metaphors, or abstractions.

Before writing each Chinese card, generate 3-5 Chinese title candidates from facts and allowed angles in the evidence packet. Pick the one that covers the core fact most cleanly. Reject titles that feel mechanically abstract or evaluative, such as `帽子戏法把答案写明了`, `最清楚的进攻答案`, `梅开二度更有说服力`, `两脚够硬`, or `这一脚来得正好`. Prefer plain core-fact labels such as `姆巴佩梅开二度`, `梅西梅开二度`, `哈兰德双响制胜`, `古伊里第81分钟制胜`, or `马扎不断接球向前`.

The active Chinese profile is `zh_matchnote_light_emotion_v1`: titles are core-fact labels, while body copy can be a match-report note plus half a sentence of light football emotion. Do not use public abstract terms such as `答案`, `理由`, `说服力`, `分量`, `走势`, `分界线`, `写下`, `证明`, `含金量`, `最稳`, `最直接`, `这张卡`, `卡片`, `模型`, or `指标压`.

Use `config/editorial/style_calibration/zh.jsonl` as the durable calibration corpus for recurring Chinese taste feedback. Treat it as examples, not a banned-word list. When copy resembles a bad example, preserve the underlying fact but rewrite toward the listed principle.

Avoid generic evaluative closers. A sentence like `这个零封很硬` or `中锋这份活干得很满` often sounds like model-added emotion because it does not add a new match fact. Prefer a concrete match consequence or fact contrast, such as `厄瓜多尔射了整场，比分还是0-0` or `日本4-0赢突尼斯，后面三粒进球都跟他有关`.

After drafting Chinese, run a strict `qu-ai-wei` style review:

- Does it sound like a Chinese football editor wrote it directly?
- Does the title cover the highest-priority fact, such as 梅开二度, 双响制胜, 制胜球, 推进, or 防守?
- Does the title avoid light-emotion phrasing that belongs in the body?
- Is there at least one concrete football action before the numbers?
- Are abstract phrases and polished-but-empty claims removed?
- Does the body avoid generic evaluative closing phrases when a concrete match consequence would say more?
- Does it avoid the active copy profile's banned public terms?
- Is every claim supported by the candidate evidence packet or SQLite?

Use `humanizer-zh` style repair only for cards that fail this review. Repair rhythm and word choice, but do not change the player selection argument.

Good:

> 哈兰德第47分钟、第57分钟各进一球，第二球后来成了制胜球。挪威最后3-2赢下来，这两脚够硬。

Bad:

> 他给了这一天一个很直接的进攻答案。更有意思的是，他的跑动和接应一直在把防线往身后拉。

## Self-Check

Before publishing, check:

- Every claim is supported by `candidate_pool.json`, `selection_decision.json`, or SQLite.
- The English and Chinese versions make the same selection argument.
- The copy does not sound like a metric table.
- Check the workflow gates: selection decision, skipped-candidate explanations, and deterministic selection validation.
- Chinese final copy should read like a from-scratch Chinese sports editor wrote it after seeing the evidence packet.
- Use `display_names.zh.display_name` when it appears in the candidate packet. Use `display_names.zh.short_name` only when that shorter, more fan-facing register is intentionally desired.
- No external match observation is implied unless an external source was actually checked.
- Avoid claims that negate an unstated alternative, such as `不是只在边路补一个进球`; the data can support the visible goal and metrics, not that contrast.
- If a card fails review, repair the local `selection_decision.json` or `copy.json`, or adjust registry config, selector/copy profile prompts, scoring, or validation, then rerun `scripts/compile_local_editorial.py --date YYYY-MM-DD`.
