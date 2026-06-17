select
  m.match_no,
  d.player_name,
  d.team,
  round(
    coalesce(d.tackles_won, 0) * 1.5
    + coalesce(d.interceptions, 0) * 1.5
    + coalesce(d.blocks, 0) * 1.0
    + coalesce(d.possession_regains, 0) * 1.3
    + coalesce(d.possession_interrupted, 0) * 1.0
    + coalesce(d.pressing_direct, 0) * 0.3
    + coalesce(d.pressing_indirect, 0) * 0.05
    + coalesce(d.clearances, 0) * 0.5,
    1
  ) as defensive_score,
  d.tackles_won,
  d.interceptions,
  d.possession_regains,
  d.possession_interrupted
from player_defensive_actions d
join matches m using(match_key)
where defensive_score > 0
order by defensive_score desc, possession_regains desc
limit 10;
