select
  m.match_no,
  d.player_name,
  d.team,
  round(
    coalesce(d.line_breaks_completed, 0) * 2.0
    + coalesce(d.ball_progressions, 0) * 1.0
    + coalesce(d.take_ons, 0) * 0.5
    + coalesce(d.step_ins, 0) * 0.5
    + coalesce(d.passes_completed, 0) * 0.02,
    1
  ) as progressor_score,
  d.line_breaks_completed,
  d.ball_progressions,
  d.take_ons,
  d.step_ins,
  d.passes_completed
from player_in_possession_distributions d
join matches m using(match_key)
where progressor_score > 0
order by progressor_score desc, line_breaks_completed desc
limit 10;
