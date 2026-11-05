{{ config(materialized='table') }}

with joined as (
    select
        s.market_date,
        coalesce(nullif(d.region, ''), 'Unknown') as region,
        coalesce(d.fuel_group, 'unclassified') as fuel_group,
        coalesce(d.fuel_chart, 'Unclassified') as fuel_chart,
        coalesce(d.dispatch_class, 'unclassified') as dispatch_class,
        s.scada_mw
    from {{ source('lake', 'silver_scada') }} as s
    left join {{ source('lake', 'silver_duid') }} as d
        on s.duid = d.duid
)
select
    market_date,
    region,
    fuel_group,
    fuel_chart,
    sum(case when scada_mw > 0 then scada_mw / 12.0 else 0 end) as mwh
from joined
where dispatch_class in ('generating', 'bidirectional', 'unclassified')
group by 1, 2, 3, 4
