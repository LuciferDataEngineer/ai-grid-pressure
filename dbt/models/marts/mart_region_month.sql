{{ config(materialized='table') }}

select
    region,
    cast(date_trunc('month', market_date) as date) as month_start,
    count(*) as intervals,
    max(total_demand_mw) as peak_mw,
    avg(total_demand_mw) as avg_mw,
    sum(rrp * total_demand_mw) / nullif(sum(total_demand_mw), 0) as demand_weighted_rrp,
    avg(rrp) as avg_rrp,
    max(rrp) as max_rrp,
    count(*) filter (where rrp >= 300) as high_price_intervals,
    count(*) filter (where rrp >= 5000) as extreme_price_intervals,
    count(*) filter (where rrp < 0) as negative_price_intervals
from {{ source('lake', 'silver_price') }}
group by 1, 2
