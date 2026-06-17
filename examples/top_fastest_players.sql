select
  player_name,
  team,
  top_speed_kmh
from player_physical_stats
where top_speed_kmh is not null
order by top_speed_kmh desc
limit 5;

