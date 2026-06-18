# Chinese Editorial Skill Evaluation

Date: 2026-06-18
Sample: 2026-06-16 Editor's Choices, six cards

## Tested Strategies

- Current Baseline: current project output after language-specific briefs.
- humanizer-zh Post-Edit: apply `humanizer-zh` rules to the current draft, emphasizing native Chinese rhythm and removing translation-like phrasing.
- qu-ai-wei Post-Edit: apply `qu-ai-wei` rules, emphasizing fact discipline, "说人话", and avoiding over-polished AI prose.
- great-writer Inspired Rewrite: use Great Writer's oral test, density/rhythm, translation immunity, and reader-value rules.
- avoid-ai-writing Style Cleanup: apply general anti-AI writing cleanup. This is mostly English-oriented but tested as a control.
- From-Scratch Chinese Sports Editor: ignore prior copy, start from the fact bank, write as a Chinese football-data editor.

## Rubric

Scores are out of 100:

- Chinese naturalness: 30
- Football specificity: 25
- Evidence discipline: 20
- Distinct angle per player: 15
- Light public-facing editorial tone: 10

Pairwise preference was used for the subjective parts. Direct scoring was used only for factual discipline.

## Score Summary

| Strategy | Score | Main Strength | Main Weakness |
|---|---:|---|---|
| From-Scratch Chinese Sports Editor | 88 | Most like a Chinese football/data post; distinct angles; least translated | Needs a separate fact-check pass because it is freer |
| qu-ai-wei Post-Edit | 82 | Blunt, clean, less abstract; good at cutting AI polish | Can become a little too clipped or colloquial |
| humanizer-zh Post-Edit | 79 | Best general Chinese rhythm repair; useful post-editor | Still preserves too much of the original skeleton |
| great-writer Inspired Rewrite | 76 | Strong sentence energy and rhythm | Tends to over-stylize and risks adding metaphorical flourishes |
| Current Baseline | 66 | Factually safe and readable | Still reads like a translated analytical brief |
| avoid-ai-writing Style Cleanup | 61 | Factually safe, removes some generic AI phrasing | Too plain; not Chinese-specific; closest to report prose |

## Pairwise Findings

### From-Scratch vs. Post-Edit

From-scratch wins most subjective comparisons. The reason is structural, not just wording: it does not inherit the current draft's sentence skeleton. It starts with how a Chinese football account would frame the moment, then inserts data.

Example:

- Post-edit: "梅西负责把比赛写进标题，德保罗负责把球送到标题附近。"
- From-scratch: "梅西把球送进网，德保罗把球送到能出事的地方。"

The latter is less polished, but more natural and more football-shaped.

### qu-ai-wei vs. humanizer-zh

`qu-ai-wei` is better as a strict reviewer. It cuts abstract phrasing harder and protects factual boundaries. `humanizer-zh` is better as a smoother post-editor when the draft is already structurally sound. In our case the draft structure is the problem, so `humanizer-zh` alone cannot solve it.

### great-writer

Great Writer gives useful diagnostics: oral test, rhythm, translation immunity, and "does this add value to the reader?" It is too broad as the main editor for daily football cards. It should influence the review checklist, not own the whole workflow.

### avoid-ai-writing

Useful for English copy and generic AI-ism detection. It is not a good Chinese football editor. It makes the text cleaner but also flatter.

## Recommendation

Use a three-role loop:

1. **Primary editor: From-Scratch Chinese Sports Editor**
   - Input: raw fact bank only, not `why_selected`, not English copy, not title candidates.
   - Output: Chinese card title and body.

2. **Strict reviewer: qu-ai-wei**
   - Checks translationese, AI polish, invented facts, over-sanitized prose, and whether the copy has at least one concrete football action.

3. **Repair editor: humanizer-zh**
   - Runs only on cards that fail the reviewer.
   - Repairs Chinese rhythm without changing the selection argument.

Do not use Great Writer as the default daily workflow. Fold its "oral test", "translation immunity", and "every sentence earns its place" checks into the super-editor rubric.

## Workflow Change Needed

The current `brief.zh.json` is still too editorialized. It includes `why_selected`, `title_candidates`, and `action_notes`, which push the editor toward the same narrative skeleton. Replace it with a rawer `fact_bank.zh.json`:

```json
{
  "player": "梅西",
  "match": "阿根廷 3-0 阿尔及利亚",
  "award": "每日最佳球员",
  "facts": [
    "阿根廷全队 3 个进球都来自梅西",
    "梅西 4 次射正",
    "梅西 12 次打穿防线"
  ],
  "allowed_angles": ["明显最佳", "不只最后一脚"],
  "forbidden_inputs": ["英文稿", "英文标题", "已成型 why_selected 句子"]
}
```

Then the super-editor loop should be:

```text
fact_bank.zh.json
  -> primary Chinese sports editor writes fresh copy
  -> qu-ai-wei style review
  -> humanizer-zh repair only if needed
  -> super-editor final factual/style check
  -> render
```

## Decision

Best standalone external skill: `qu-ai-wei` as reviewer.

Best overall workflow: from-scratch Chinese sports editor plus `qu-ai-wei` review, with `humanizer-zh` as fallback repair.

Main lesson: skills can improve sentences, but they cannot fully fix a bad upstream brief. We need to stop giving Chinese editors a pre-written narrative skeleton.
