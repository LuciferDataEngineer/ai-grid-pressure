{{ config(materialized='table') }}

select
    region || '|' || cast(market_date as varchar) as region_day_key,
    region,
    market_date,
    count(*) as intervals,
    max(total_demand_mw) as peak_mw,
    avg(total_demand_mw) as avg_mw,
    min(total_demand_mw) as min_mw,
    arg_max(interval_end, total_demand_mw) as peak_interval_end,
    arg_max(interval_end, rrp) as max_price_interval_end,
    avg(rrp) as avg_rrp,
    sum(rrp * total_demand_mw) / nullif(sum(total_demand_mw), 0) as demand_weighted_rrp,
    max(rrp) as max_rrp,
    min(rrp) as min_rrp,
    count(*) filter (where rrp >= 300) as high_price_intervals,
    count(*) filter (where rrp >= 5000) as extreme_price_intervals,
    count(*) filter (where rrp < 0) as negative_price_intervals,
    avg(rrp) filter (where hour_of_day between 16 and 20) as evening_avg_rrp,
    avg(total_demand_mw) filter (where hour_of_day between 16 and 20) as evening_avg_mw,
    avg(rrp) filter (where hour_of_day between 10 and 13) as midday_avg_rrp,
    avg(total_demand_mw) filter (where hour_of_day between 10 and 13) as midday_avg_mw,
    min(total_demand_mw) filter (where hour_of_day between 0 and 4) as overnight_min_mw
from {{ source('lake', 'silver_price') }}
group by region, market_date
