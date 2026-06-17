select
  player_name,
  team,
  total_distance_m
from player_physical_stats
where total_distance_m is not null
order by total_distance_m desc
limit 5;

