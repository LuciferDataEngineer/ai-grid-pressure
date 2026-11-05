select region, market_date, peak_mw, avg_mw, min_mw
from {{ ref('mart_region_day') }}
where peak_mw < avg_mw - 0.05
   or avg_mw < min_mw - 0.05
