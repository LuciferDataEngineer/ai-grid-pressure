{{ config(materialized='table') }}

select
    period_start,
    quarter,
    index_id,
    index_name,
    region_code,
    region_name,
    value,
    value / lag(value, 4) over (
        partition by index_id, region_code
        order by period_start
    ) - 1 as yoy_pct
from {{ source('lake', 'silver_cpi') }}
