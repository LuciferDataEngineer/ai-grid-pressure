from datetime import datetime

from gridpressure.timeutil import format_nem, hour_of_day, market_date, parse_nem_timestamp


def test_midnight_belongs_to_previous_market_date():
    moment = parse_nem_timestamp("2026/11/05 00:00:00")
    assert moment == datetime(2026, 11, 5, 0, 0)
    assert market_date(moment).isoformat() == "2026-11-04"
    assert hour_of_day(moment) == 23


def test_twenty_four_hundred_is_next_midnight():
    moment = parse_nem_timestamp("2026/11/04 24:00:00")
    assert moment == datetime(2026, 11, 5, 0, 0)
    assert market_date(moment).isoformat() == "2026-11-04"


def test_ordinary_interval():
    moment = parse_nem_timestamp("2026/11/04 18:30:00")
    assert market_date(moment).isoformat() == "2026-11-04"
    assert hour_of_day(moment) == 18
    assert "6:30pm NEM time" in format_nem(moment)
