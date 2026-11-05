select *
from {{ ref('mart_fuel_day') }}
where mwh < 0
