{{ config(materialized='table') }}

select
    rate_date,
    cash_rate_target
from {{ source('lake', 'silver_cash') }}
