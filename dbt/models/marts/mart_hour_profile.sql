{{ config(materialized='table') }}

with bounds as (
    select max(market_date) as end_date
    from {{ source('lake', 'silver_price') }}
)
select
    region,
    hour_of_day,
    avg(total_demand_mw) as avg_mw,
    avg(rrp) as avg_rrp,
    sum(rrp * total_demand_mw) / nullif(sum(total_demand_mw), 0) as demand_weighted_rrp
from {{ source('lake', 'silver_price') }}
cross join bounds
where market_date >= end_date - interval 89 day
group by 1, 2
