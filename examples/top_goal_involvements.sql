with involvements as (
  select scorer_name as player, team_name as team, 1 as goals, 0 as assists
  from goal_involvements
  union all
  select assister_name as player, team_name as team, 0 as goals, 1 as assists
  from goal_involvements
  where assister_name is not null
)
select
  player,
  team,
  sum(goals) as goals,
  sum(assists) as assists,
  sum(goals + assists) as goal_involvements
from involvements
group by upper(player), team
order by goal_involvements desc, goals desc, assists desc, player
limit 10;
