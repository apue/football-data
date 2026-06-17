select
  m.match_no,
  s.team,
  s.minute,
  s.player_name,
  s.outcome,
  s.body_part,
  s.delivery_type
from shots s
join matches m using(match_key)
where s.is_goal = 1 or s.is_on_target = 1
order by m.match_no, s.minute;

