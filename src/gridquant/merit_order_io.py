import json
from dataclasses import dataclass
from pathlib import Path

from gridquant.merit_order import GeneratorOffer


@dataclass(frozen=True)
class MeritOrderCase:
    name: str
    description: str
    generators: list[GeneratorOffer]
    demand_mw: float
    duration_hours: float


def load_merit_order_case(path: Path) -> MeritOrderCase:
    raw = json.loads(path.read_text(encoding="utf-8"))

    if raw.get("schema_version") != 1:
        raise ValueError("Unsupported merit-order example schema.")

    generators = [
        GeneratorOffer(
            name=item["name"],
            capacity_mw=item["capacity_mw"],
            marginal_cost_per_mwh=item["marginal_cost_per_mwh"],
        )
        for item in raw["generators"]
    ]

    return MeritOrderCase(
        name=raw["name"],
        description=raw.get("description", ""),
        generators=generators,
        demand_mw=raw["demand_mw"],
        duration_hours=raw.get("duration_hours", 1.0),
    )