import json
from datetime import UTC, datetime, timedelta
from math import isfinite
from urllib.parse import urlencode
from urllib.request import urlopen

from gridquant.data.models import PriceInterval

PRICE_ENDPOINT = "https://api.energy-charts.info/v2/price"


def fetch_price_response(start_date: str, end_date: str) -> bytes:
    """Download the original DE-LU price response for the requested dates."""
    parameters = {
        "bzn": "DE-LU",
        "start": start_date,
        "end": end_date,
    }
    url = PRICE_ENDPOINT + "?" + urlencode(parameters)

    with urlopen(url, timeout=30) as response:
        raw_bytes: bytes = response.read()

    return raw_bytes


def parse_price_response(raw_json: str) -> list[PriceInterval]:
    """Convert JSON text into a list of PriceInterval objects."""
    data = json.loads(raw_json)
    intervals: list[PriceInterval] = []

    # Input Validation: Ensure the response contains the expected fields.
    if not isinstance(data, dict):
        raise TypeError("Expected a JSON object.")

    if data.get("endpoint") != "price":
        raise ValueError("Expected a price response.")

    if data.get("bidding_zone") != "DE-LU":
        raise ValueError("Expected bidding zone DE-LU.")

    if data.get("unit") != "EUR / MWh":
        raise ValueError("Expected price unit EUR / MWh.")

    interval_minutes = data.get("interval_minutes")

    if (
        isinstance(interval_minutes, bool)
        or not isinstance(interval_minutes, int)
        or interval_minutes <= 0
    ):
        raise ValueError("Interval minutes must be a positive integer.")

    records = data.get("data")

    if not isinstance(records, list):
        raise TypeError("Expected data to be a list.")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"Record {index}: expected an object.")

        timestamp = record.get("timestamp")

        if not isinstance(timestamp, str):
            raise ValueError(f"Record {index}: timestamp must be text.")

        try:
            start = datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise ValueError(f"Record {index}: invalid timestamp.") from exc

        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError(f"Record {index}: timestamp must include a UTC offset.")

        values = record.get("values")

        if not isinstance(values, dict):
            raise TypeError(f"Record {index}: expected a values object.")

        price = values.get("day_ahead_price")

        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError(f"Record {index}: price must be a number.")

        if not isfinite(price):
            raise ValueError(f"Record {index}: price must be finite.")

        start_utc = start.astimezone(UTC)
        end_utc = start_utc + timedelta(minutes=interval_minutes)

        intervals.append(
            PriceInterval(
                delivery_start_utc=start_utc,
                delivery_end_utc=end_utc,
                price_eur_per_mwh=float(price),
                bidding_zone=data["bidding_zone"],
            )
        )

    return intervals
