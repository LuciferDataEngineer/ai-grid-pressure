{{ config(materialized='table') }}

with timed as (
    select
        interval_end,
        market_date,
        sum(total_demand_mw) as demand_mw,
        sum(rrp * total_demand_mw) / nullif(sum(total_demand_mw), 0) as vw_rrp,
        max(rrp) as max_rrp,
        min(rrp) as min_rrp
    from {{ source('lake', 'silver_price') }}
    group by 1, 2
)
select
    market_date,
    count(*) as intervals,
    max(demand_mw) as peak_mw,
    avg(demand_mw) as avg_mw,
    min(demand_mw) as min_mw,
    arg_max(interval_end, demand_mw) as peak_interval_end,
    sum(vw_rrp * demand_mw) / nullif(sum(demand_mw), 0) as demand_weighted_rrp,
    max(max_rrp) as max_rrp,
    count(*) filter (where vw_rrp >= 300) as high_price_intervals,
    count(*) filter (where min_rrp < 0) as negative_price_intervals
from timed
group by 1
