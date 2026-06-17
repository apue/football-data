select
  m.match_no,
  t.team,
  t.possession_pct,
  t.passes_total,
  t.completed_line_breaks,
  t.receptions_final_third,
  t.attempts_total,
  t.xg,
  t.goals
from team_match_stats t
join matches m using(match_key)
order by m.match_no, t.team;

