# Narrative Style

Editor’s Choices are not dashboard prose. Write like a data-aware football editor.

## Principles

- Lead with the judgment, then give the reason.
- Use at most two or three hard numbers in each body paragraph.
- Translate metrics into football language:
  - `goals >= 3`: hat-trick / 帽子戏法
  - `line_breaks_completed` plus `ball_progressions`: breaking lines, carrying through pressure / 打穿防线、推进过压力区
  - `offers_received`, `in_between`, `in_behind`: finding pockets, receiving between lines / 在防线之间接应、身后接应
  - `possession_regains`, `possession_interrupted`: disrupting rhythm, winning the ball back / 打断节奏、夺回球权
- Do not pretend to have watched video. Say “PMSR profile”, “data profile”, or “数据画像” when the claim comes from data.
- Do not list every metric. Keep detailed components in JSON for audit.
- Hidden Gem is optional. If the evidence is not strong, do not force one.

## English Tone

Use compact editorial language. Avoid hype unless the evidence is obvious.

Good:

> The hat-trick gives Messi the headline, but the PMSR profile makes the choice feel less like a popularity vote and more like the day’s cleanest attacking case.

Bad:

> Messi had 3 goals, 6 shots, 4 shots on target, 16 receptions, 9 in-behind offers, and a score of 37.5.

## Chinese Tone

Use natural Chinese sports commentary. Do not mirror the English sentence by sentence.

Good:

> 梅西这场不用复杂包装：帽子戏法本身就是最直接的比赛叙事。更重要的是，PMSR 的进攻画像也支持这个判断。

Bad:

> 梅西有 3 个进球、6 次射门、4 次射正、16 次接应、9 次身后接应，所以他得分最高。

## Self-Check

Before publishing, check:

- Every claim is supported by `choices.json` or SQLite.
- The English and Chinese versions make the same selection argument.
- The copy does not sound like a metric table.
- No external match observation is implied unless an external source was actually checked.
