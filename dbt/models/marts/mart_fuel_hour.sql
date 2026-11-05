{{ config(materialized='table') }}

with joined as (
    select
        s.market_date,
        s.hour_of_day,
        coalesce(d.fuel_chart, 'Unclassified') as fuel_chart,
        coalesce(d.dispatch_class, 'unclassified') as dispatch_class,
        s.scada_mw
    from {{ source('lake', 'silver_scada') }} as s
    left join {{ source('lake', 'silver_duid') }} as d
        on s.duid = d.duid
),
daily as (
    select
        market_date,
        hour_of_day,
        fuel_chart,
        sum(case when scada_mw > 0 then scada_mw / 12.0 else 0 end) as mwh
    from joined
    where dispatch_class in ('generating', 'bidirectional', 'unclassified')
    group by 1, 2, 3
)
select
    hour_of_day,
    fuel_chart,
    sum(mwh) / count(distinct market_date) as avg_mwh
from daily
group by 1, 2
