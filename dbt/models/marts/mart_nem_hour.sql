{{ config(materialized='table') }}

with bounds as (
    select max(market_date) as end_date
    from {{ source('lake', 'silver_price') }}
),
timed as (
    select
        hour_of_day,
        sum(total_demand_mw) as demand_mw,
        sum(rrp * total_demand_mw) / nullif(sum(total_demand_mw), 0) as vw_rrp
    from {{ source('lake', 'silver_price') }}
    cross join bounds
    where market_date >= end_date - interval 89 day
    group by hour_of_day, interval_end
)
select
    hour_of_day,
    avg(demand_mw) as avg_mw,
    sum(vw_rrp * demand_mw) / nullif(sum(demand_mw), 0) as demand_weighted_rrp
from timed
group by 1
