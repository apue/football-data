select
  m.match_no,
  o.player_name,
  o.team,
  round(
    coalesce(o.offers_received, 0) * 1.0
    + coalesce(o.in_behind, 0) * 0.6
    + coalesce(o.in_between, 0) * 0.4
    + coalesce(o.total_offers, 0) * 0.1,
    1
  ) as receiver_score,
  o.total_offers,
  o.offers_received,
  o.in_behind,
  o.in_between
from player_offers_receptions o
join matches m using(match_key)
where receiver_score > 0
order by receiver_score desc, offers_received desc
limit 10;
