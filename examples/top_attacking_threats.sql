with shot_totals as (
  select
    match_key,
    team,
    upper(player_name) as player_name,
    count(*) as shots,
    sum(is_on_target) as on_target,
    sum(is_goal) as goals
  from shots
  group by match_key, team, upper(player_name)
)
select
  m.match_no,
  a.player_name,
  a.team,
  a.position,
  round(
    coalesce(s.goals, 0) * 6.0
    + coalesce(s.on_target, 0) * 2.0
    + coalesce(d.attempts_at_goal, 0) * 1.0
    + coalesce(o.offers_received, 0) * 0.20
    + coalesce(o.in_behind, 0) * 0.25,
    1
  ) as threat_score,
  coalesce(s.shots, d.attempts_at_goal, 0) as shots,
  coalesce(s.on_target, 0) as on_target,
  coalesce(o.offers_received, 0) as offers_received,
  coalesce(o.in_behind, 0) as in_behind
from player_appearances a
join matches m using(match_key)
left join player_in_possession_distributions d
  on d.match_key = a.match_key
 and d.team = a.team
 and d.player_no = a.player_no
left join player_offers_receptions o
  on o.match_key = a.match_key
 and o.team = a.team
 and o.player_no = a.player_no
left join shot_totals s
  on s.match_key = a.match_key
 and s.team = a.team
 and s.player_name = upper(a.player_name)
where threat_score > 0
order by threat_score desc, shots desc
limit 10;
