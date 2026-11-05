# Grid pressure: what the public numbers say

This note is generated from the warehouse after each build. Every figure comes from the committed AEMO, ABS and RBA snapshot. Nothing here is a modelled data-centre megawatt.

## The question

Power, not chips, is the constraint people are arguing about as data-centre projects pile up. The public wholesale market cannot name those projects. It can show where demand is already peaking, where five-minute prices jump or go negative, how metered generation was split in a recent fortnight, and how fast household electricity prices have risen.

## Window

- Wholesale prices and regional demand: 1 Nov 2024 to 5 Nov 2026.
- Recent window used for 'last 90 days': 8 Aug 2026 to 5 Nov 2026.
- Metered generation: 22 Oct 2026 to 4 Nov 2026 (14 days).
- Consumer price index through 2026-Q3. Cash rate target as at 5 Nov 2026.
- Times are NEM time, Australian Eastern Standard Time (UTC+10) all year.

## Demand

The highest state demand in the extract is 13,159 MW in New South Wales at 1 Jul 2025, 5:50pm NEM time. The highest moment for the five regions added together is 33,674 MW at 16 Dec 2024, 5:30pm NEM time. Adding the regions is reasonable for AEMO total demand because interconnector flows cancel. The figure still excludes most rooftop solar, so it is grid demand, not all electricity used behind the meter.

Average daily peak, last 90 days versus the same 90 days a year earlier:

| State | Last 90 days | A year earlier | Change | Average overnight minimum, last 90 days |
| --- | ---: | ---: | ---: | ---: |
| New South Wales | 9,001 | 9,377 | -4.0% | 6,546 |
| Queensland | 7,539 | 7,787 | -3.2% | 5,468 |
| Victoria | 6,616 | 6,422 | +3.0% | 4,485 |
| South Australia | 1,679 | 1,799 | -6.6% | 1,242 |
| Tasmania | 1,227 | 1,239 | -0.9% | 923 |

A rising overnight minimum would be the fingerprint of flat new load. Read the column as a description, not a cause. The files do not split data centres out of the total.

## Wholesale prices

A high price in this briefing is $300 per megawatt-hour or more, the marker long used in Australian Energy Regulator wholesale reporting. It is an analysis choice, not an AEMO product.

| State | High-price periods | Share | Prices below zero | Demand-weighted price | 4pm–9pm | 10am–2pm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| New South Wales | 88 | 0.34% | 1,133 | 95.50 | 105.87 | 49.89 |
| Queensland | 63 | 0.24% | 3,115 | 77.53 | 100.18 | 28.44 |
| Victoria | 14 | 0.05% | 5,312 | 55.94 | 75.02 | 10.24 |
| South Australia | 16 | 0.06% | 6,760 | 64.67 | 76.15 | -1.59 |
| Tasmania | 18 | 0.07% | 4,009 | 56.31 | 74.25 | 20.96 |

The highest wholesale price in the extract is $23,200 per megawatt-hour, reached 2 times: Tasmania at 13 Jul 2026, 4:20pm NEM time; New South Wales at 10 Oct 2026, 7:20am NEM time.
New South Wales accounts for the most high prices in the last 90 days. South Australia accounts for the most prices below zero.
Across states, the last-90-day evening average was $86.32 and the middle-of-day average was $21.64.

## Fuel mix

The generation window is short on purpose: fourteen daily public SCADA archives, 22 Oct 2026 to 4 Nov 2026, joined to the AEMO registration list for fuel. Positive metered output is turned into energy by treating each reading as a five-minute average (`megawatts / 12`).

Renewable share of matched metered output, batteries excluded: **37.0%**. Battery discharge: **230,981 MWh**. Unclassified share: **0.3%**.

| State | Renewable share of matched output |
| --- | ---: |
| New South Wales | 36.1% |
| Queensland | 24.2% |
| Victoria | 36.5% |
| South Australia | 73.6% |
| Tasmania | 99.3% |

Group totals (megawatt-hours, positive output only):

- fossil: 4,333,236 MWh
- renewable: 2,552,216 MWh
- storage: 230,981 MWh
- unclassified: 19,395 MWh

## Household prices and the cash rate

The national electricity consumer price index rose 10.6% over the year to 2026-Q3. The all-groups index rose 3.9%. The ABS API extract used here publishes electricity at national level; capital-city all-groups indexes are on the bills tab for the broader cost of living.

The Reserve Bank cash rate target was 4.85% on 5 Nov 2026. It moved from 4.60% on 4 Nov 2026.

Wholesale prices and the consumer price index are different things. One is a five-minute market price. The other is a quarterly household price index. Both are in this briefing because ministers and households feel them together, not because one is a simple pass-through of the other.

## What not to conclude

- Do not treat a state peak as proof that a data centre caused it.
- Do not treat the renewable share as the share of all electricity. Rooftop solar is largely missing, and the window is two weeks.
- Do not treat the Deloitte investment headline as a megawatt forecast. It is context in the README only.
- Do not shift the clock times forward an hour in summer. NEM time does not use daylight saving.

