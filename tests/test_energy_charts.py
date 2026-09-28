import json
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from gridquant.collectors.energy_charts import parse_price_response


def test_parse_price_response() -> None:
    # A small synthetic response with two 15-minute intervals.
    raw_json = json.dumps(
        {
            "schema_version": "2.0",
            "endpoint": "price",
            "bidding_zone": "DE-LU",
            "timezone": "Europe/Berlin",
            "unit": "EUR / MWh",
            "interval_minutes": 15,
            "data": [
                {
                    "timestamp": "2026-09-26T00:00:00+02:00",
                    "values": {"day_ahead_price": 40.0},
                },
                {
                    "timestamp": "2026-09-26T00:15:00+02:00",
                    "values": {"day_ahead_price": -10.0},
                },
            ],
        }
    )

    intervals = parse_price_response(raw_json)

    assert len(intervals) == 2

    first, second = intervals

    # Midnight at UTC+02:00 is 22:00 UTC on the previous day.
    assert first.delivery_start_utc == datetime(2026, 9, 25, 22, 0, tzinfo=UTC)
    assert first.delivery_end_utc == datetime(2026, 9, 25, 22, 15, tzinfo=UTC)
    assert first.price_eur_per_mwh == 40.0
    assert first.bidding_zone == "DE-LU"

    # Consecutive intervals meet at the same boundary.
    assert second.delivery_start_utc == first.delivery_end_utc
    assert second.delivery_end_utc == datetime(2026, 9, 25, 22, 30, tzinfo=UTC)

    # Negative prices are valid and must be preserved.
    assert second.price_eur_per_mwh == -10.0
    assert second.bidding_zone == "DE-LU"


@pytest.mark.parametrize(
    "field, invalid_value, expected_error",
    [
        ("bidding_zone", "FR", "Expected bidding zone"),
        ("unit", "EUR/kWh", "Expected price unit"),
        ("interval_minutes", 0, "positive integer"),
        ("interval_minutes", -15, "positive integer"),
        ("interval_minutes", True, "positive integer"),
        ("interval_minutes", "15", "positive integer"),
        ("interval_minutes", None, "positive integer"),
    ],
)
def test_rejects_invalid_metadata(
    field: str,
    invalid_value: object,
    expected_error: str,
) -> None:
    response: dict[str, object] = {
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "unit": "EUR / MWh",
        "interval_minutes": 15,
        "data": [],
    }
    response[field] = invalid_value

    with pytest.raises(ValueError, match=expected_error):
        parse_price_response(json.dumps(response))


@pytest.mark.parametrize(
    "price",
    [None, True, "40.0", float("nan"), float("inf"), -float("inf")],
)
def test_rejects_invalid_prices(price: object) -> None:
    response = {
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "unit": "EUR / MWh",
        "interval_minutes": 15,
        "data": [
            {
                "timestamp": "2026-09-26T00:00:00+02:00",
                "values": {"day_ahead_price": price},
            }
        ],
    }

    with pytest.raises(ValueError, match="price must"):
        parse_price_response(json.dumps(response))


@pytest.mark.parametrize(
    "timestamp",
    [
        None,
        "not-a-date",
        "2026-09-26T00:00:00",
    ],
)
def test_rejects_invalid_timestamps(timestamp: object) -> None:
    response = {
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "unit": "EUR / MWh",
        "interval_minutes": 15,
        "data": [
            {
                "timestamp": timestamp,
                "values": {"day_ahead_price": 40.0},
            }
        ],
    }

    with pytest.raises(ValueError, match="timestamp"):
        parse_price_response(json.dumps(response))


@pytest.mark.parametrize(
    "timestamps, expected_start",
    [
        pytest.param(
            ["2023-02-15T00:00:00+01:00", "2023-02-15T00:15:00+01:00"],
            datetime(2023, 2, 14, 23, 0, tzinfo=UTC),
            id="ordinary",
        ),
        pytest.param(
            ["2023-03-26T01:45:00+01:00", "2023-03-26T03:00:00+02:00"],
            datetime(2023, 3, 26, 0, 45, tzinfo=UTC),
            id="spring-skipped-hour",
        ),
        pytest.param(
            ["2023-10-29T02:45:00+02:00", "2023-10-29T02:00:00+01:00"],
            datetime(2023, 10, 29, 0, 45, tzinfo=UTC),
            id="autumn-repeated-hour",
        ),
    ],
)
def test_clock_changes_preserve_elapsed_time(
    timestamps: list[str], expected_start: datetime
) -> None:
    response = {
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "unit": "EUR / MWh",
        "interval_minutes": 15,
        "data": [
            {"timestamp": timestamp, "values": {"day_ahead_price": price}}
            for timestamp, price in zip(timestamps, [40.0, -10.0], strict=True)
        ],
    }
    first, second = parse_price_response(json.dumps(response))

    assert first.delivery_start_utc == expected_start
    assert first.delivery_end_utc == expected_start + timedelta(minutes=15)
    assert second.delivery_start_utc == first.delivery_end_utc
    assert second.delivery_end_utc == expected_start + timedelta(minutes=30)
    assert first.price_eur_per_mwh == 40.0
    assert second.price_eur_per_mwh == -10.0


@pytest.mark.parametrize("interval_minutes", [60, 15], ids=["hourly", "quarter-hourly"])
@pytest.mark.parametrize(
    "delivery_date, local_hours, expected_start, expected_end, expected_hours",
    [
        pytest.param(
            "2023-02-15",
            [(hour, "+01:00") for hour in range(24)],
            datetime(2023, 2, 14, 23, tzinfo=UTC),
            datetime(2023, 2, 15, 23, tzinfo=UTC),
            24,
            id="ordinary-day",
        ),
        pytest.param(
            "2023-03-26",
            [(hour, "+01:00") for hour in range(2)]
            + [(hour, "+02:00") for hour in range(3, 24)],
            datetime(2023, 3, 25, 23, tzinfo=UTC),
            datetime(2023, 3, 26, 22, tzinfo=UTC),
            23,
            id="spring-23-hour-day",
        ),
        pytest.param(
            "2023-10-29",
            [(hour, "+02:00") for hour in range(3)]
            + [(hour, "+01:00") for hour in range(2, 24)],
            datetime(2023, 10, 28, 22, tzinfo=UTC),
            datetime(2023, 10, 29, 23, tzinfo=UTC),
            25,
            id="autumn-25-hour-day",
        ),
    ],
)
def test_full_delivery_day_coverage(
    interval_minutes: int,
    delivery_date: str,
    local_hours: list[tuple[int, str]],
    expected_start: datetime,
    expected_end: datetime,
    expected_hours: int,
) -> None:
    # Explicit Berlin wall-clock hours form synthetic fixtures, independent of
    # the parser's UTC arithmetic. These are not historical market observations.
    timestamps = [
        f"{delivery_date}T{hour:02d}:{minute:02d}:00{offset}"
        for hour, offset in local_hours
        for minute in range(0, 60, interval_minutes)
    ]
    response = {
        "schema_version": "2.0",
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "timezone": "Europe/Berlin",
        "unit": "EUR / MWh",
        "interval_minutes": interval_minutes,
        "data": [
            {"timestamp": timestamp, "values": {"day_ahead_price": float(index)}}
            for index, timestamp in enumerate(timestamps)
        ],
    }
    intervals = parse_price_response(json.dumps(response))
    duration = timedelta(minutes=interval_minutes)
    expected_count = expected_hours * 60 // interval_minutes

    assert len(intervals) == expected_count
    assert intervals[0].delivery_start_utc == expected_start
    assert intervals[-1].delivery_end_utc == expected_end

    starts = [interval.delivery_start_utc for interval in intervals]
    assert len(set(starts)) == expected_count  # Includes both autumn 02:00 hours.
    assert starts == sorted(starts)

    for index, interval in enumerate(intervals):
        # Compare the entire UTC grid, not only the record count or boundaries.
        assert interval.delivery_start_utc == expected_start + index * duration
        assert interval.delivery_end_utc == expected_start + (index + 1) * duration
        assert interval.delivery_start_utc.utcoffset() == timedelta(0)
        assert interval.delivery_end_utc.utcoffset() == timedelta(0)
        assert interval.price_eur_per_mwh == float(index)
        assert interval.bidding_zone == "DE-LU"

    for previous, current in pairwise(intervals):
        assert previous.delivery_end_utc == current.delivery_start_utc

    assert (
        sum(
            (interval.delivery_end_utc - interval.delivery_start_utc).total_seconds()
            for interval in intervals
        )
        == expected_hours * 3600
    )


@pytest.mark.parametrize(
    "field, invalid_value, expected_error",
    [
        ("endpoint", "public_power", "Expected a price response"),
        ("endpoint", None, "Expected a price response"),
    ],
)
def test_rejects_unsupported_response(
    field: str,
    invalid_value: object,
    expected_error: str,
) -> None:
    response: dict[str, object] = {
        "schema_version": "2.0",
        "endpoint": "price",
        "bidding_zone": "DE-LU",
        "unit": "EUR / MWh",
        "interval_minutes": 15,
        "data": [],
    }
    response[field] = invalid_value

    with pytest.raises(ValueError, match=expected_error):
        parse_price_response(json.dumps(response))
