"""Plain-English briefing built only from warehouse query results."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from gridpressure.config import DOCS, DUCKDB_PATH, HIGH_PRICE_AUD, REGION_NAMES, ROOT
from gridpressure.timeutil import format_date, format_nem

ORDER = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
FUEL_ORDER = [
    "Coal",
    "Brown coal",
    "Gas",
    "Other fossil",
    "Hydro",
    "Wind",
    "Solar",
    "Other renewable",
    "Storage",
    "Other",
    "Unclassified",
]


def _load() -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    names = [
        "mart_region_day",
        "mart_region_month",
        "mart_nem_day",
        "mart_hour_profile",
        "mart_nem_hour",
        "mart_fuel_day",
        "mart_fuel_hour",
        "mart_cpi",
        "mart_cash",
    ]
    frames = {name: con.execute(f"SELECT * FROM {name}").fetchdf() for name in names}
    con.close()
    for frame in frames.values():
        for column in frame.columns:
            if str(frame[column].dtype).startswith("datetime"):
                frame[column] = pd.to_datetime(frame[column])
    return frames


def _f(value) -> float:
    return float(value)


def _mw(value: float) -> str:
    return f"{value:,.0f} MW"


def _aud(value: float) -> str:
    if abs(value) >= 100:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def _pct(value: float) -> str:
    return f"{value:.1f}%"


def _count(value: int) -> str:
    return f"{value:,}"


def _status(share: float) -> str:
    if share >= 0.01:
        return "stress"
    if share >= 0.002:
        return "watch"
    return "calm"


def _name(region: str) -> str:
    return REGION_NAMES[region]


def _hour_label(hour: int) -> str:
    suffix = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return f"{hour12}{suffix}"


def _month_label(value) -> str:
    moment = pd.Timestamp(value)
    return moment.strftime("%b %Y")


def build_briefing() -> dict:
    frames = _load()
    day = frames["mart_region_day"].copy()
    day["market_date"] = pd.to_datetime(day["market_date"])
    end = day["market_date"].max()
    start = day["market_date"].min()
    recent_start = end - pd.Timedelta(days=89)
    recent = day[day["market_date"] >= recent_start]
    prior_end = end - pd.Timedelta(days=365)
    prior_start = prior_end - pd.Timedelta(days=89)
    prior = day[(day["market_date"] >= prior_start) & (day["market_date"] <= prior_end)]

    nem = frames["mart_nem_day"].copy()
    nem["market_date"] = pd.to_datetime(nem["market_date"])
    nem_recent = nem[nem["market_date"] >= recent_start].sort_values("market_date")

    month = frames["mart_region_month"].copy()
    month["month_start"] = pd.to_datetime(month["month_start"])
    hours = frames["mart_hour_profile"].copy()
    nem_hours = frames["mart_nem_hour"].sort_values("hour_of_day")
    fuel_day = frames["mart_fuel_day"].copy()
    fuel_day["market_date"] = pd.to_datetime(fuel_day["market_date"])
    fuel_hour = frames["mart_fuel_hour"].copy()
    cpi = frames["mart_cpi"].copy()
    cpi["period_start"] = pd.to_datetime(cpi["period_start"])
    cash = frames["mart_cash"].sort_values("rate_date")

    region_stats = []
    for region in ORDER:
        part = recent[recent["region"] == region]
        intervals = int(part["intervals"].sum())
        high = int(part["high_price_intervals"].sum())
        negative = int(part["negative_price_intervals"].sum())
        demand = part["avg_mw"] * part["intervals"]
        weighted = float((part["demand_weighted_rrp"] * demand).sum() / demand.sum())
        evening = float(
            (part["evening_avg_rrp"] * part["intervals"]).sum() / part["intervals"].sum()
        )
        midday = float((part["midday_avg_rrp"] * part["intervals"]).sum() / part["intervals"].sum())
        prior_part = prior[prior["region"] == region]
        region_stats.append(
            {
                "region": region,
                "name": _name(region),
                "intervals": intervals,
                "high": high,
                "high_share": high / intervals if intervals else 0,
                "negative": negative,
                "negative_share": negative / intervals if intervals else 0,
                "weighted": weighted,
                "evening": evening,
                "midday": midday,
                "peak": float(day.loc[day["region"] == region, "peak_mw"].max()),
                "recent_peak": float(part["peak_mw"].max()),
                "recent_avg_peak": float(part["peak_mw"].mean()),
                "prior_avg_peak": float(prior_part["peak_mw"].mean()) if len(prior_part) else None,
                "recent_overnight": float(part["overnight_min_mw"].mean()),
                "prior_overnight": (
                    float(prior_part["overnight_min_mw"].mean()) if len(prior_part) else None
                ),
            }
        )
    by_region = {row["region"]: row for row in region_stats}
    hottest = max(region_stats, key=lambda row: row["high"])
    most_negative = max(region_stats, key=lambda row: row["negative"])
    highest_peak_row = day.loc[day["peak_mw"].idxmax()]
    nem_peak_row = nem.loc[nem["peak_mw"].idxmax()]
    cap_rows = day[day["max_rrp"] == day["max_rrp"].max()].sort_values("max_price_interval_end")
    dearest_names = []
    dearest_whens = []
    for _, cap_row in cap_rows.iterrows():
        name = _name(str(cap_row["region"]))
        if name not in dearest_names:
            dearest_names.append(name)
        dearest_whens.append(
            f"{name} at {format_nem(pd.Timestamp(cap_row['max_price_interval_end']).to_pydatetime())}"
        )

    fuel_start = fuel_day["market_date"].min()
    fuel_end = fuel_day["market_date"].max()
    fuel_group = fuel_day.groupby("fuel_group", as_index=False)["mwh"].sum()
    fuel_totals = {
        str(key): float(value)
        for key, value in zip(fuel_group["fuel_group"], fuel_group["mwh"], strict=True)
    }
    generation = sum(
        fuel_totals.get(name, 0) for name in ("renewable", "fossil", "other", "unclassified")
    )
    renewable_share = fuel_totals.get("renewable", 0) / generation if generation else 0
    unclassified_share = fuel_totals.get("unclassified", 0) / generation if generation else 0
    storage_mwh = fuel_totals.get("storage", 0)
    fuel_by_region = []
    for region in ORDER:
        part = fuel_day[fuel_day["region"] == region]
        totals = {
            str(key): float(value) for key, value in part.groupby("fuel_group")["mwh"].sum().items()
        }
        gen = sum(totals.get(name, 0) for name in ("renewable", "fossil", "other", "unclassified"))
        fuel_by_region.append(
            {
                "region": region,
                "name": _name(region),
                "renewable_share": (totals.get("renewable", 0) / gen) if gen else 0,
                "mwh": gen,
            }
        )

    elec = cpi[(cpi["index_id"] == "40055") & (cpi["region_code"] == "50")].sort_values(
        "period_start"
    )
    groups = cpi[(cpi["index_id"] == "10001") & (cpi["region_code"] == "50")].sort_values(
        "period_start"
    )
    latest_elec = elec.dropna(subset=["yoy_pct"]).iloc[-1]
    latest_groups = groups.dropna(subset=["yoy_pct"]).iloc[-1]
    cash_known = cash.dropna(subset=["cash_rate_target"])
    latest_cash = cash_known.iloc[-1]
    latest_rate = float(latest_cash["cash_rate_target"])
    previous_cash = cash_known[cash_known["cash_rate_target"] != latest_rate]
    previous_rate = (
        float(previous_cash.iloc[-1]["cash_rate_target"]) if len(previous_cash) else None
    )
    if len(previous_cash):
        changed_on = cash_known.loc[cash_known.index > previous_cash.index[-1]].iloc[0]
        cash_changed_on = format_date(pd.Timestamp(changed_on["rate_date"]).date())
    else:
        cash_changed_on = format_date(pd.Timestamp(latest_cash["rate_date"]).date())

    nem_evening = float(
        (recent["evening_avg_rrp"] * recent["intervals"]).sum() / recent["intervals"].sum()
    )
    nem_midday = float(
        (recent["midday_avg_rrp"] * recent["intervals"]).sum() / recent["intervals"].sum()
    )
    nem_weighted = float(
        (nem_recent["demand_weighted_rrp"] * nem_recent["avg_mw"]).sum()
        / nem_recent["avg_mw"].sum()
    )

    facts = {
        "price_start": format_date(start.date()),
        "price_end": format_date(end.date()),
        "recent_start": format_date(recent_start.date()),
        "fuel_start": format_date(fuel_start.date()),
        "fuel_end": format_date(fuel_end.date()),
        "fuel_days": int(fuel_day["market_date"].nunique()),
        "high_price": HIGH_PRICE_AUD,
        "hottest": hottest,
        "most_negative": most_negative,
        "regions": region_stats,
        "peak_region": _name(str(highest_peak_row["region"])),
        "peak_mw": float(highest_peak_row["peak_mw"]),
        "peak_when": format_nem(
            pd.Timestamp(highest_peak_row["peak_interval_end"]).to_pydatetime()
        ),
        "dearest_region": " and ".join(dearest_names),
        "dearest_rrp": float(cap_rows["max_rrp"].iloc[0]),
        "dearest_when": "; ".join(dearest_whens),
        "dearest_count": int(len(cap_rows)),
        "nem_peak_mw": float(nem_peak_row["peak_mw"]),
        "nem_peak_when": format_nem(
            pd.Timestamp(nem_peak_row["peak_interval_end"]).to_pydatetime()
        ),
        "nem_weighted_90": nem_weighted,
        "nem_evening": nem_evening,
        "nem_midday": nem_midday,
        "renewable_share": renewable_share,
        "unclassified_share": unclassified_share,
        "storage_mwh": storage_mwh,
        "fuel_by_region": fuel_by_region,
        "fuel_totals": fuel_totals,
        "elec_yoy": float(latest_elec["yoy_pct"]) * 100,
        "cpi_yoy": float(latest_groups["yoy_pct"]) * 100,
        "cpi_quarter": str(latest_elec["quarter"]),
        "cash_rate": latest_rate,
        "cash_date": format_date(pd.Timestamp(latest_cash["rate_date"]).date()),
        "cash_changed_on": cash_changed_on,
        "cash_previous": previous_rate,
        "by_region": by_region,
    }
    dashboard = _dashboard(facts, day, month, hours, nem_hours, nem_recent, fuel_hour, cpi, cash)
    return {"facts": _jsonable(facts), "dashboard": dashboard}


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        if value != value:
            return None
        return round(value, 6)
    if hasattr(value, "item"):
        return _jsonable(value.item())
    return value


def _series(names: list[str], rows: dict[str, list]) -> list[dict]:
    return [
        {"name": name, "data": [None if pd.isna(v) else round(float(v), 2) for v in rows[name]]}
        for name in names
    ]


def _dashboard(facts, day, month, hours, nem_hours, nem_recent, fuel_hour, cpi, cash) -> dict:
    regions = facts["regions"]
    map_regions = []
    for row in regions:
        share = row["high_share"] * 100
        map_regions.append(
            {
                "id": row["region"],
                "name": row["name"],
                "value": _pct(share) if share >= 0.1 else f"{share:.2f}%",
                "caption": f"of prices at or above ${int(facts['high_price'])}",
                "status": _status(row["high_share"]),
            }
        )
    hottest = facts["hottest"]
    quarter_plain = _quarter_plain(facts["cpi_quarter"])
    cash_move = ""
    if facts["cash_previous"] is not None:
        cash_move = f" It moved from {facts['cash_previous']:.2f}% on {facts['cash_changed_on']}."
    evening_sentence = (
        f"From 4pm to 9pm the average wholesale price across the states was {_aud(facts['nem_evening'])} "
        f"per megawatt-hour. From 10am to 2pm it was {_aud(facts['nem_midday'])}."
    )
    if facts["nem_evening"] > facts["nem_midday"] * 1.05:
        evening_sentence += " Evening power has been clearly dearer than the middle of the day."
    elif facts["nem_midday"] > facts["nem_evening"] * 1.05:
        evening_sentence += (
            " The middle of the day has been dearer than the evening in this window."
        )
    else:
        evening_sentence += " Those two parts of the day have been close."

    overview = {
        "id": "overview",
        "label": "Overview",
        "banner": (
            "Where the grid is tight while a large wave of data-centre investment is being planned. "
            "The public figures do not label data-centre load on their own. They show which states are "
            "peaking, where wholesale prices jump, and how household electricity prices have moved."
        ),
        "kpis": [
            _kpi(
                "Highest state demand",
                _mw(facts["peak_mw"]),
                f"{facts['peak_region']}, {facts['peak_when']}",
                "The highest five-minute grid demand in any state in this briefing.",
                "stress",
            ),
            _kpi(
                "Whole-market peak",
                _mw(facts["nem_peak_mw"]),
                facts["nem_peak_when"],
                "The five states added together, at the busiest moment.",
                "watch",
            ),
            _kpi(
                "Highest wholesale price",
                _aud(facts["dearest_rrp"]),
                facts["dearest_region"],
                facts["dearest_when"] + ". Dollars per megawatt-hour.",
                "stress" if facts["dearest_rrp"] >= facts["high_price"] else "watch",
            ),
            _kpi(
                "Household power prices",
                _pct(facts["elec_yoy"]),
                f"Year to {quarter_plain}",
                f"Electricity in the consumer price index. Overall prices rose {_pct(facts['cpi_yoy'])}.",
                "stress" if facts["elec_yoy"] > facts["cpi_yoy"] + 2 else "watch",
            ),
            _kpi(
                "Cash rate target",
                f"{facts['cash_rate']:.2f}%",
                facts["cash_date"],
                "Reserve Bank cash rate target." + cash_move,
                "watch",
            ),
        ],
        "hero": {
            "kind": "map",
            "title": "Where high wholesale prices have clustered",
            "insight": (
                f"Since {facts['recent_start']}, {hottest['name']} has had the most five-minute prices "
                f"at or above ${int(facts['high_price'])}: {_count(hottest['high'])} times."
            ),
            "regions": map_regions,
        },
        "charts": [
            _line_chart(
                "Grid demand on the busiest moment of each recent day",
                "Each point is the highest five-minute demand that day, for the five states combined.",
                "Megawatts",
                [format_date(ts.date()) for ts in nem_recent["market_date"]],
                [
                    {
                        "name": "National Electricity Market",
                        "data": [round(_f(v), 1) for v in nem_recent["peak_mw"]],
                    }
                ],
            ),
            _month_price_chart(month),
            _cpi_level_chart(cpi),
        ],
        "meaning": (
            f"The tightest wholesale prices in the last 90 days were in {hottest['name']}. "
            f"{evening_sentence} Household electricity prices rose {_pct(facts['elec_yoy'])} "
            f"over the year to {quarter_plain}, faster than the {_pct(facts['cpi_yoy'])} rise in overall prices. "
            "That is the pressure households feel. It is not a measure of any single data centre."
        ),
        "sources": _sources(facts),
    }
    demand = _demand_tab(facts, day, hours)
    prices = _prices_tab(facts, month, nem_hours)
    fuel = _fuel_tab(facts, fuel_hour)
    bills = _bills_tab(facts, cpi, cash)
    actions = _actions_tab(facts, quarter_plain, cash_move, evening_sentence)
    return {
        "title": "Grid pressure briefing",
        "subtitle": "National Electricity Market",
        "as_of": f"Wholesale market through {facts['price_end']}",
        "time_note": (
            "Clock times are NEM time: Australian Eastern Standard Time, UTC+10, "
            "with no shift for daylight saving. During daylight saving that is one hour "
            "behind Melbourne and Sydney clocks."
        ),
        "tabs": [overview, demand, prices, fuel, bills, actions],
    }


def _aud_plain(value: float) -> str:
    return f"{value:.0f}"


def _quarter_plain(quarter: str) -> str:
    year, q = quarter.split("-Q")
    names = {"1": "March", "2": "June", "3": "September", "4": "December"}
    return f"the {names.get(q, q)} quarter {year}"


def _kpi(label, value, detail, note, status) -> dict:
    return {"label": label, "value": value, "detail": detail, "note": note, "status": status}


def _line_chart(title, insight, y_label, x, series) -> dict:
    return {
        "title": title,
        "insight": insight,
        "kind": "line",
        "y_label": y_label,
        "x": x,
        "series": series,
    }


def _bar_chart(title, insight, y_label, x, series) -> dict:
    return {
        "title": title,
        "insight": insight,
        "kind": "bar",
        "y_label": y_label,
        "x": x,
        "series": series,
    }


def _stacked_chart(title, insight, y_label, x, series) -> dict:
    return {
        "title": title,
        "insight": insight,
        "kind": "stacked",
        "y_label": y_label,
        "x": x,
        "series": series,
    }


def _month_price_chart(month: pd.DataFrame) -> dict:
    months = sorted(month["month_start"].unique())
    labels = [_month_label(value) for value in months]
    series = []
    for region in ORDER:
        part = month[month["region"] == region].set_index("month_start")
        series.append(
            {
                "name": _name(region),
                "data": [
                    None
                    if moment not in part.index
                    else round(_f(part.loc[moment, "demand_weighted_rrp"]), 2)
                    for moment in months
                ],
            }
        )
    return _line_chart(
        "Wholesale price by state, weighted by demand",
        "A month with a few very high prices and heavy demand pulls this line up.",
        "Dollars per megawatt-hour",
        labels,
        series,
    )


def _cpi_level_chart(cpi: pd.DataFrame) -> dict:
    elec = cpi[(cpi["index_id"] == "40055") & (cpi["region_code"] == "50")].sort_values(
        "period_start"
    )
    groups = cpi[(cpi["index_id"] == "10001") & (cpi["region_code"] == "50")].sort_values(
        "period_start"
    )
    base_period = pd.Timestamp("2019-01-01")

    def rebase(frame):
        base_rows = frame[frame["period_start"] == base_period]
        base = (
            float(base_rows["value"].iloc[0]) if len(base_rows) else float(frame["value"].iloc[0])
        )
        return [round(float(value) / base * 100, 2) for value in frame["value"]]

    labels = [pd.Timestamp(v).strftime("%b %Y") for v in elec["period_start"]]
    group_lookup = dict(
        zip((pd.Timestamp(v) for v in groups["period_start"]), rebase(groups), strict=False)
    )
    return _line_chart(
        "Household electricity prices compared with the cost of living",
        "Both lines start at 100 in the March quarter 2019. A higher line means a bigger rise since then.",
        "Index, March quarter 2019 = 100",
        labels,
        [
            {"name": "Electricity", "data": rebase(elec)},
            {
                "name": "All prices",
                "data": [group_lookup.get(pd.Timestamp(v)) for v in elec["period_start"]],
            },
        ],
    )


def _demand_tab(facts, day, hours) -> dict:
    end = pd.to_datetime(day["market_date"]).max()
    recent_start = end - pd.Timedelta(days=89)
    recent = day[pd.to_datetime(day["market_date"]) >= recent_start]
    # last 120 days of regional peaks would be dense; use monthly peaks instead as support
    peak_bits = []
    for row in facts["regions"]:
        change = None
        if row["prior_avg_peak"]:
            change = (row["recent_avg_peak"] / row["prior_avg_peak"] - 1) * 100
        peak_bits.append((row, change))
    fastest = max(peak_bits, key=lambda item: item[1] if item[1] is not None else -999)
    dates = sorted(pd.to_datetime(recent["market_date"]).unique())
    # Thin to every day but chart only last 90, five lines. 90 points is fine.
    labels = [format_date(pd.Timestamp(value).date()) for value in dates]
    series = []
    for region in ORDER:
        part = recent[recent["region"] == region]
        lookup = {
            pd.Timestamp(moment): peak
            for moment, peak in zip(part["market_date"], part["peak_mw"], strict=True)
        }
        series.append(
            {
                "name": _name(region),
                "data": [
                    round(float(lookup[pd.Timestamp(value)]), 1)
                    if pd.Timestamp(value) in lookup
                    else None
                    for value in dates
                ],
            }
        )
    hour_labels = [_hour_label(hour) for hour in range(24)]
    hour_series = []
    for region in ORDER:
        part = hours[hours["region"] == region].set_index("hour_of_day")
        hour_series.append(
            {
                "name": _name(region),
                "data": [
                    None if hour not in part.index else round(_f(part.loc[hour, "avg_mw"]), 1)
                    for hour in range(24)
                ],
            }
        )
    change_text = "not available"
    if fastest[1] is not None:
        change_text = (
            f"{fastest[0]['name']} shows the largest change in its typical daily peak "
            f"versus the same 90 days a year earlier: {fastest[1]:+.1f}%."
        )
    return {
        "id": "demand",
        "label": "Demand stress",
        "banner": (
            f"Grid demand from {facts['price_start']} to {facts['price_end']}. "
            "This is the demand AEMO uses in the wholesale market. It does not include most rooftop solar."
        ),
        "kpis": [
            _kpi(
                "Highest in the briefing",
                _mw(facts["peak_mw"]),
                f"{facts['peak_region']}, {facts['peak_when']}",
                "Five-minute grid demand, one state.",
                "stress",
            ),
            _kpi(
                "Busiest moment for the whole market",
                _mw(facts["nem_peak_mw"]),
                facts["nem_peak_when"],
                "Sum of the five state demands at the same moment.",
                "watch",
            ),
            _kpi(
                "Typical daily peak, last 90 days",
                _mw(
                    float(
                        sum(row["recent_avg_peak"] for row in facts["regions"])
                        / len(facts["regions"])
                    )
                ),
                "Average of the five states' own daily peaks",
                "Not the whole-market peak. Each state is averaged on its own.",
                "calm",
            ),
            _kpi(
                "Change versus a year earlier",
                f"{fastest[1]:+.1f}%" if fastest[1] is not None else "n/a",
                fastest[0]["name"],
                "Change in the average daily peak, same 90-day span a year earlier.",
                "watch" if fastest[1] and fastest[1] > 0 else "calm",
            ),
        ],
        "hero": _line_chart(
            "Daily peak demand in each state",
            "The top of each day since " + facts["recent_start"] + ".",
            "Megawatts",
            labels,
            series,
        ),
        "charts": [
            _line_chart(
                "When demand usually sits through the day",
                "Average demand by hour over the last 90 days, in NEM time.",
                "Megawatts",
                hour_labels,
                hour_series,
            ),
            _bar_chart(
                "Average daily peak now, and a year earlier",
                change_text,
                "Megawatts",
                [row["name"] for row in facts["regions"]],
                [
                    {
                        "name": "Last 90 days",
                        "data": [round(row["recent_avg_peak"], 1) for row in facts["regions"]],
                    },
                    {
                        "name": "Same 90 days a year earlier",
                        "data": [
                            None
                            if row["prior_avg_peak"] is None
                            else round(row["prior_avg_peak"], 1)
                            for row in facts["regions"]
                        ],
                    },
                ],
            ),
        ],
        "meaning": (
            f"The highest state demand in this briefing was {_mw(facts['peak_mw'])} in {facts['peak_region']} "
            f"at {facts['peak_when']}. {change_text} "
            "A new always-on load would lift the overnight floor as well as the evening peak. "
            "These public totals cannot show how much of today's floor is already data centres."
        ),
        "sources": _sources(facts),
    }


def _prices_tab(facts, month, nem_hours) -> dict:
    hottest = facts["hottest"]
    negative = facts["most_negative"]
    hour_labels = [_hour_label(hour) for hour in range(24)]
    return {
        "id": "prices",
        "label": "Prices",
        "banner": (
            f"Wholesale prices from {facts['price_start']} to {facts['price_end']}, "
            "in dollars per megawatt-hour. A high price here means $300 or more."
        ),
        "kpis": [
            _kpi(
                "Most prices at or above $300",
                _count(hottest["high"]),
                hottest["name"],
                f"Five-minute periods since {facts['recent_start']}.",
                "stress",
            ),
            _kpi(
                "Share of time at that level",
                _pct(hottest["high_share"] * 100)
                if hottest["high_share"] >= 0.001
                else f"{hottest['high_share'] * 100:.2f}%",
                hottest["name"],
                "Share of five-minute prices in the last 90 days.",
                _status(hottest["high_share"]),
            ),
            _kpi(
                "Most time below zero",
                _count(negative["negative"]),
                negative["name"],
                "Five-minute prices below $0 in the last 90 days. Generators were paying to stay on.",
                "watch",
            ),
            _kpi(
                "Recent whole-market average",
                _aud(facts["nem_weighted_90"]),
                "Last 90 days, weighted by demand",
                "The price weighted by how much power the market was using.",
                "watch",
            ),
        ],
        "hero": _month_price_chart(month),
        "charts": [
            _line_chart(
                "Wholesale price through a typical day",
                "Demand-weighted price by hour for the last 90 days, five states combined.",
                "Dollars per megawatt-hour",
                hour_labels,
                [
                    {
                        "name": "National Electricity Market",
                        "data": [
                            round(_f(value), 2)
                            for value in nem_hours.sort_values("hour_of_day")["demand_weighted_rrp"]
                        ],
                    }
                ],
            ),
            _bar_chart(
                "How often each state hit a high price",
                f"Count of five-minute prices at or above ${int(facts['high_price'])} since {facts['recent_start']}.",
                "Five-minute periods",
                [row["name"] for row in facts["regions"]],
                [{"name": "High prices", "data": [row["high"] for row in facts["regions"]]}],
            ),
            _bar_chart(
                "How often the wholesale price was below zero",
                "These are the periods when extra flexible use would have been paid to consume, or at least not charged.",
                "Five-minute periods",
                [row["name"] for row in facts["regions"]],
                [
                    {
                        "name": "Prices below zero",
                        "data": [row["negative"] for row in facts["regions"]],
                    }
                ],
            ),
        ],
        "meaning": (
            f"{hottest['name']} has seen the most prices at or above ${int(facts['high_price'])} "
            f"since {facts['recent_start']}: {_count(hottest['high'])} five-minute periods. "
            f"{negative['name']} has seen the most prices below zero: {_count(negative['negative'])}. "
            f"Across the market, the evening average was {_aud(facts['nem_evening'])} and the middle-of-day "
            f"average was {_aud(facts['nem_midday'])}."
        ),
        "sources": _sources(facts),
    }


def _fuel_tab(facts, fuel_hour) -> dict:
    labels = [_hour_label(hour) for hour in range(24)]
    present = [name for name in FUEL_ORDER if name in set(fuel_hour["fuel_chart"])]
    series = []
    for name in present:
        part = fuel_hour[fuel_hour["fuel_chart"] == name].set_index("hour_of_day")
        series.append(
            {
                "name": name,
                "data": [
                    0 if hour not in part.index else round(_f(part.loc[hour, "avg_mwh"]), 2)
                    for hour in range(24)
                ],
            }
        )
    unclassified = ""
    if facts["unclassified_share"] >= 0.02:
        unclassified = (
            f" {_pct(facts['unclassified_share'] * 100)} of metered output could not be matched "
            "to a fuel in the registration list and is shown separately."
        )
    return {
        "id": "fuel",
        "label": "Fuel mix",
        "banner": (
            f"Metered output of registered power stations from {facts['fuel_start']} to {facts['fuel_end']} "
            f"({facts['fuel_days']} days). Rooftop solar is not in these figures."
        ),
        "kpis": [
            _kpi(
                "Renewable share of metered output",
                _pct(facts["renewable_share"] * 100),
                f"{facts['fuel_start']} to {facts['fuel_end']}",
                "Wind, solar, hydro and other renewable fuels. Batteries are not in this share.",
                "calm" if facts["renewable_share"] >= 0.4 else "watch",
            ),
            _kpi(
                "Highest renewable share",
                _pct(max(row["renewable_share"] for row in facts["fuel_by_region"]) * 100),
                max(facts["fuel_by_region"], key=lambda row: row["renewable_share"])["name"],
                "Share of that state's matched metered output.",
                "calm",
            ),
            _kpi(
                "Lowest renewable share",
                _pct(min(row["renewable_share"] for row in facts["fuel_by_region"]) * 100),
                min(facts["fuel_by_region"], key=lambda row: row["renewable_share"])["name"],
                "Coal and gas make up more of the metered output here.",
                "watch",
            ),
            _kpi(
                "Battery discharge",
                f"{facts['storage_mwh']:,.0f} MWh",
                "Shown separately from generation",
                "Energy discharged by batteries. Charging is not counted as generation.",
                "calm",
            ),
        ],
        "hero": _stacked_chart(
            "What was generating through an average day",
            "Average energy in each hour across the days in this fuel window. NEM time.",
            "Megawatt-hours",
            labels,
            series,
        ),
        "charts": [
            _bar_chart(
                "Renewable share of metered output by state",
                "The same short window, split by state.",
                "Percent",
                [row["name"] for row in facts["fuel_by_region"]],
                [
                    {
                        "name": "Renewables",
                        "data": [
                            round(row["renewable_share"] * 100, 1)
                            for row in facts["fuel_by_region"]
                        ],
                    }
                ],
            )
        ],
        "meaning": (
            f"Over these {facts['fuel_days']} days, {_pct(facts['renewable_share'] * 100)} of matched "
            f"metered output came from renewables. Batteries discharged about {facts['storage_mwh']:,.0f} "
            f"megawatt-hours, counted on their own."
            + unclassified
            + " This is a recent fortnight, not a verdict on the whole year."
        ),
        "sources": _sources(facts),
    }


def _bills_tab(facts, cpi, cash) -> dict:
    quarter = _quarter_plain(facts["cpi_quarter"])
    latest = cpi[(cpi["index_id"] == "10001") & (cpi["region_code"] != "50")].dropna(
        subset=["yoy_pct"]
    )
    latest = latest.sort_values("period_start").groupby("region_name", as_index=False).tail(1)
    cash_recent = cash[pd.to_datetime(cash["rate_date"]) >= "2023-01-01"]
    return {
        "id": "bills",
        "label": "Bills & CPI",
        "banner": (
            "Household electricity prices from the consumer price index, next to the cash rate. "
            "The electricity index used here is the national figure. City figures below are the overall cost of living."
        ),
        "kpis": [
            _kpi(
                "Electricity prices, past year",
                _pct(facts["elec_yoy"]),
                quarter,
                "Change in the national electricity consumer price index.",
                "stress" if facts["elec_yoy"] > 5 else "watch",
            ),
            _kpi(
                "Overall prices, past year",
                _pct(facts["cpi_yoy"]),
                quarter,
                "Change in the all-groups consumer price index for Australia.",
                "watch",
            ),
            _kpi(
                "Gap",
                _pct(facts["elec_yoy"] - facts["cpi_yoy"]),
                "Electricity minus overall prices",
                "How much faster electricity moved than the general cost of living.",
                "stress" if facts["elec_yoy"] - facts["cpi_yoy"] > 2 else "watch",
            ),
            _kpi(
                "Cash rate target",
                f"{facts['cash_rate']:.2f}%",
                facts["cash_date"],
                (
                    f"Changed from {facts['cash_previous']:.2f}%."
                    if facts["cash_previous"] is not None
                    else "Reserve Bank target."
                ),
                "watch",
            ),
        ],
        "hero": _cpi_level_chart(cpi),
        "charts": [
            _bar_chart(
                "Cost of living by city, past year",
                f"All-groups consumer price index to {quarter}. This is not the electricity index.",
                "Percent change from a year earlier",
                list(latest["region_name"]),
                [
                    {
                        "name": "All prices",
                        "data": [round(float(v) * 100, 2) for v in latest["yoy_pct"]],
                    }
                ],
            ),
            _line_chart(
                "Cash rate target since 2023",
                "The Reserve Bank's target, in percent.",
                "Percent",
                [format_date(pd.Timestamp(v).date()) for v in cash_recent["rate_date"]],
                [
                    {
                        "name": "Cash rate target",
                        "data": [round(float(v), 2) for v in cash_recent["cash_rate_target"]],
                    }
                ],
            ),
        ],
        "meaning": (
            f"Over the year to {quarter}, electricity in the consumer price index rose {_pct(facts['elec_yoy'])}. "
            f"Overall consumer prices rose {_pct(facts['cpi_yoy'])}. "
            f"The cash rate target was {facts['cash_rate']:.2f}% on {facts['cash_date']}. "
            "Households are living with both. Wholesale spikes do not pass into bills one-for-one, "
            "but a year of dearer electricity already has."
        ),
        "sources": _sources(facts),
    }


def _actions_tab(facts, quarter, cash_move, evening_sentence) -> dict:
    hottest = facts["hottest"]
    negative = facts["most_negative"]
    return {
        "id": "actions",
        "label": "Actions",
        "banner": "What the figures support. Nothing here assumes a data centre caused a price spike.",
        "kpis": [
            _kpi(
                "Watch first",
                hottest["name"],
                f"{_count(hottest['high'])} high prices in 90 days",
                "The state where wholesale prices reached $300 most often.",
                "stress",
            ),
            _kpi(
                "Flexible-load opening",
                negative["name"],
                f"{_count(negative['negative'])} prices below zero",
                "The state with the most five-minute prices below zero.",
                "calm",
            ),
            _kpi(
                "Bill pressure",
                _pct(facts["elec_yoy"]),
                quarter,
                "National electricity consumer price index, change over the year.",
                "stress",
            ),
            _kpi(
                "Evening versus middle of the day",
                _aud(facts["nem_evening"] - facts["nem_midday"]),
                "Difference in average wholesale price",
                "Positive means the evening was dearer.",
                "watch" if facts["nem_evening"] > facts["nem_midday"] else "calm",
            ),
        ],
        "hero": _bar_chart(
            "Where high wholesale prices showed up",
            f"Five-minute prices at or above ${int(facts['high_price'])}, last 90 days.",
            "Five-minute periods",
            [row["name"] for row in facts["regions"]],
            [{"name": "High prices", "data": [row["high"] for row in facts["regions"]]}],
        ),
        "charts": [
            _bar_chart(
                "Evening price and middle-of-day price",
                "Average wholesale price, last 90 days.",
                "Dollars per megawatt-hour",
                [row["name"] for row in facts["regions"]],
                [
                    {
                        "name": "4pm to 9pm",
                        "data": [round(row["evening"], 2) for row in facts["regions"]],
                    },
                    {
                        "name": "10am to 2pm",
                        "data": [round(row["midday"], 2) for row in facts["regions"]],
                    },
                ],
            ),
            _bar_chart(
                "Electricity prices versus the cost of living",
                f"Change over the year to {quarter}.",
                "Percent",
                ["Electricity", "All prices"],
                [
                    {
                        "name": "Past year",
                        "data": [round(facts["elec_yoy"], 2), round(facts["cpi_yoy"], 2)],
                    }
                ],
            ),
        ],
        "meaning": " ".join(
            [
                f"Ministers and the regulator: the wholesale heat in the last 90 days is sharpest in {hottest['name']}. That is the first place to test whether new always-on load can be shifted, interrupted, or paired with new supply.",
                f"There is also a surplus signal in {negative['name']}, which had {_count(negative['negative'])} five-minute prices below zero. Daytime flexibility is worth more there than a flat around-the-clock load.",
                evening_sentence,
                f"Households: electricity prices rose {_pct(facts['elec_yoy'])} over the year to {quarter}, against {_pct(facts['cpi_yoy'])} for prices overall. The cash rate target is {facts['cash_rate']:.2f}%.{cash_move} Using less power between 4pm and 9pm is the step that lines up with the dearer part of the wholesale day.",
                "Do not read any of these totals as the output of a named data centre. The market does not publish that split.",
            ]
        ),
        "sources": _sources(facts),
    }


def _sources(facts) -> str:
    return (
        f"Sources: AEMO price and demand, {facts['price_start']} to {facts['price_end']}; "
        f"AEMO metered generation, {facts['fuel_start']} to {facts['fuel_end']}; "
        f"ABS consumer price index to {facts['cpi_quarter']}; "
        f"RBA cash rate target to {facts['cash_date']}. "
        "Free public files. No account and no paid feed."
    )


def write_documents(payload: dict) -> None:
    dashboard = payload["dashboard"]
    facts = payload["facts"]
    data_dir = DOCS / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "dashboard.json").write_text(
        json.dumps(dashboard, indent=2) + "\n", encoding="utf-8"
    )
    (DOCS / "evidence" / "facts.json").parent.mkdir(parents=True, exist_ok=True)
    (DOCS / "evidence" / "facts.json").write_text(
        json.dumps(facts, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "INSIGHTS.md").write_text(_insights(facts), encoding="utf-8")
    _patch_readme(facts)
    _copy_site()


def _copy_site() -> None:
    import shutil

    DOCS.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copyfile(ROOT / "dashboard" / name, DOCS / name)
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")


def _patch_readme(facts: dict) -> None:
    path = ROOT / "README.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    block = _readme_facts(facts)
    start = "<!-- FACTS:START -->"
    end = "<!-- FACTS:END -->"
    if start in text and end in text:
        text = text[: text.index(start)] + start + "\n\n" + block + "\n\n" + text[text.index(end) :]
    path.write_text(text, encoding="utf-8")


def _readme_facts(facts: dict) -> str:
    hottest = facts["hottest"]
    negative = facts["most_negative"]
    return "\n".join(
        [
            f"- Highest state demand in the extract: **{_mw(facts['peak_mw'])}** in **{facts['peak_region']}** at {facts['peak_when']}.",
            f"- Highest whole-market demand (five regions added): **{_mw(facts['nem_peak_mw'])}** at {facts['nem_peak_when']}.",
            f"- Highest wholesale price: **{_aud(facts['dearest_rrp'])} per megawatt-hour**, reached {facts['dearest_count']} times ({facts['dearest_when']}).",
            f"- Since {facts['recent_start']}, **{hottest['name']}** had the most prices at or above ${int(facts['high_price'])}: **{_count(hottest['high'])}** five-minute periods ({hottest['high_share'] * 100:.2f}% of the time).",
            f"- **{negative['name']}** had the most prices below zero: **{_count(negative['negative'])}**.",
            f"- Last-90-day evening average wholesale price **{_aud(facts['nem_evening'])}**, middle-of-day average **{_aud(facts['nem_midday'])}**.",
            f"- Metered renewable share {facts['fuel_start']} to {facts['fuel_end']}: **{_pct(facts['renewable_share'] * 100)}** (batteries excluded; rooftop solar not in the file).",
            f"- National electricity CPI rose **{_pct(facts['elec_yoy'])}** over the year to {facts['cpi_quarter']}; all-groups CPI rose **{_pct(facts['cpi_yoy'])}**.",
            f"- RBA cash rate target **{facts['cash_rate']:.2f}%** on {facts['cash_date']}"
            + (
                f". It moved from {facts['cash_previous']:.2f}% on {facts['cash_changed_on']}."
                if facts["cash_previous"] is not None
                else "."
            ),
        ]
    )


def _insights(facts: dict) -> str:
    lines = [
        "# Grid pressure: what the public numbers say",
        "",
        "This note is generated from the warehouse after each build. Every figure comes from the committed AEMO, ABS and RBA snapshot. Nothing here is a modelled data-centre megawatt.",
        "",
        "## The question",
        "",
        "Power, not chips, is the constraint people are arguing about as data-centre projects pile up. The public wholesale market cannot name those projects. It can show where demand is already peaking, where five-minute prices jump or go negative, how metered generation was split in a recent fortnight, and how fast household electricity prices have risen.",
        "",
        "## Window",
        "",
        f"- Wholesale prices and regional demand: {facts['price_start']} to {facts['price_end']}.",
        f"- Recent window used for 'last 90 days': {facts['recent_start']} to {facts['price_end']}.",
        f"- Metered generation: {facts['fuel_start']} to {facts['fuel_end']} ({facts['fuel_days']} days).",
        f"- Consumer price index through {facts['cpi_quarter']}. Cash rate target as at {facts['cash_date']}.",
        "- Times are NEM time, Australian Eastern Standard Time (UTC+10) all year.",
        "",
        "## Demand",
        "",
        f"The highest state demand in the extract is {_mw(facts['peak_mw'])} in {facts['peak_region']} at {facts['peak_when']}. The highest moment for the five regions added together is {_mw(facts['nem_peak_mw'])} at {facts['nem_peak_when']}. Adding the regions is reasonable for AEMO total demand because interconnector flows cancel. The figure still excludes most rooftop solar, so it is grid demand, not all electricity used behind the meter.",
        "",
        "Average daily peak, last 90 days versus the same 90 days a year earlier:",
        "",
        "| State | Last 90 days | A year earlier | Change | Average overnight minimum, last 90 days |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in facts["regions"]:
        prior = "n/a" if row["prior_avg_peak"] is None else f"{row['prior_avg_peak']:,.0f}"
        change = (
            "n/a"
            if row["prior_avg_peak"] in (None, 0)
            else f"{(row['recent_avg_peak'] / row['prior_avg_peak'] - 1) * 100:+.1f}%"
        )
        lines.append(
            f"| {row['name']} | {row['recent_avg_peak']:,.0f} | {prior} | {change} | {row['recent_overnight']:,.0f} |"
        )
    lines += [
        "",
        "A rising overnight minimum would be the fingerprint of flat new load. Read the column as a description, not a cause. The files do not split data centres out of the total.",
        "",
        "## Wholesale prices",
        "",
        f"A high price in this briefing is ${int(facts['high_price'])} per megawatt-hour or more, the marker long used in Australian Energy Regulator wholesale reporting. It is an analysis choice, not an AEMO product.",
        "",
        "| State | High-price periods | Share | Prices below zero | Demand-weighted price | 4pm–9pm | 10am–2pm |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in facts["regions"]:
        lines.append(
            f"| {row['name']} | {row['high']:,} | {row['high_share'] * 100:.2f}% | {row['negative']:,} | "
            f"{row['weighted']:.2f} | {row['evening']:.2f} | {row['midday']:.2f} |"
        )
    hottest = facts["hottest"]
    negative = facts["most_negative"]
    lines += [
        "",
        f"The highest wholesale price in the extract is {_aud(facts['dearest_rrp'])} per megawatt-hour, reached {facts['dearest_count']} times: {facts['dearest_when']}.",
        f"{hottest['name']} accounts for the most high prices in the last 90 days. {negative['name']} accounts for the most prices below zero.",
        f"Across states, the last-90-day evening average was {_aud(facts['nem_evening'])} and the middle-of-day average was {_aud(facts['nem_midday'])}.",
        "",
        "## Fuel mix",
        "",
        f"The generation window is short on purpose: fourteen daily public SCADA archives, {facts['fuel_start']} to {facts['fuel_end']}, joined to the AEMO registration list for fuel. Positive metered output is turned into energy by treating each reading as a five-minute average (`megawatts / 12`).",
        "",
        f"Renewable share of matched metered output, batteries excluded: **{_pct(facts['renewable_share'] * 100)}**. Battery discharge: **{facts['storage_mwh']:,.0f} MWh**. Unclassified share: **{_pct(facts['unclassified_share'] * 100)}**.",
        "",
        "| State | Renewable share of matched output |",
        "| --- | ---: |",
    ]
    for row in facts["fuel_by_region"]:
        lines.append(f"| {row['name']} | {row['renewable_share'] * 100:.1f}% |")
    lines += [
        "",
        "Group totals (megawatt-hours, positive output only):",
        "",
    ]
    for key, value in sorted(facts["fuel_totals"].items(), key=lambda item: -item[1]):
        lines.append(f"- {key}: {value:,.0f} MWh")
    lines += [
        "",
        "## Household prices and the cash rate",
        "",
        f"The national electricity consumer price index rose {_pct(facts['elec_yoy'])} over the year to {facts['cpi_quarter']}. The all-groups index rose {_pct(facts['cpi_yoy'])}. The ABS API extract used here publishes electricity at national level; capital-city all-groups indexes are on the bills tab for the broader cost of living.",
        "",
        f"The Reserve Bank cash rate target was {facts['cash_rate']:.2f}% on {facts['cash_date']}"
        + (
            f". It moved from {facts['cash_previous']:.2f}% on {facts['cash_changed_on']}."
            if facts["cash_previous"] is not None
            else "."
        ),
        "",
        "Wholesale prices and the consumer price index are different things. One is a five-minute market price. The other is a quarterly household price index. Both are in this briefing because ministers and households feel them together, not because one is a simple pass-through of the other.",
        "",
        "## What not to conclude",
        "",
        "- Do not treat a state peak as proof that a data centre caused it.",
        "- Do not treat the renewable share as the share of all electricity. Rooftop solar is largely missing, and the window is two weeks.",
        "- Do not treat the Deloitte investment headline as a megawatt forecast. It is context in the README only.",
        "- Do not shift the clock times forward an hour in summer. NEM time does not use daylight saving.",
        "",
    ]
    return "\n".join(lines) + "\n"
