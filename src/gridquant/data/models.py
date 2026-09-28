from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceInterval:
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    price_eur_per_mwh: float
    bidding_zone: str