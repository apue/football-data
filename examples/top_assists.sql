select
  assister_name as player,
  team_name as team,
  count(*) as assists
from goal_involvements
where assister_name is not null
group by upper(assister_name), team_name
order by assists desc, player
limit 10;
