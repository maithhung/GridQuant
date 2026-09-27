from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class GeneratorOffer:
    """Represents offer from a generator in the merit order."""

    name: str
    capacity_mw: float  # in MW
    marginal_cost_per_mwh: float  # in eur/MWh


@dataclass(frozen=True)
class MarketResult:
    """Represents the result of a market dispatch."""

    dispatch_mw: dict[
        str, float
    ]  # store each generator identity and its dispatched in MW
    clearing_price_per_mwh: (
        float | None
    )  # in eur/MWh | None if no market clearing price is determined
    cleared_volume_mw: float  # Total dispatched power in MW
    cleared_energy_mwh: float  # Delivered energy: cleared_volume_mw * duration_hours
    unmet_demand_mw: float  # Unserved power in MW
    unmet_energy_mwh: float  # Unserved energy: unmet_demand_mw * duration_hours
    operating_profit_eur: dict[str, float] | None


def validate_number(value: float, name: str) -> None:
    """Reject booleans, non-numeric values, NaN, and infinity."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, not a boolean.")

    if not isfinite(value):
        raise ValueError(f"{name} must be finite.")


def clear_market(
    generators: list[GeneratorOffer],
    demand_mw: float,
    duration_hours: float = 1.0,
) -> MarketResult:
    """Clears the market based on the merit order of generator offers.

    Args:
        generators (list[GeneratorOffer]): Offers sorted internally by marginal cost.
        demand_mw (float): Total demand in MW.
        duration_hours (float): Duration of the market clearing in hours.

    Returns:
        MarketResult: Dispatch/cleared/unmet power in MW, energy in MWh,
            clearing price in EUR/MWh, and operating profit in EUR.
    """
    # Check for duplicate generator names
    seen_names: set[str] = set()

    for generator in generators:
        if generator.name in seen_names:
            raise ValueError(f"Duplicate generator name found: {generator.name}")
        seen_names.add(generator.name)

    # Validate demand and duration
    validate_number(demand_mw, "Demand")
    validate_number(duration_hours, "Duration")

    if demand_mw < 0:
        raise ValueError("Demand must be nonnegative.")

    if duration_hours <= 0:
        raise ValueError("Duration must be positive.")

    # Validate each generator's numeric fields
    for generator in generators:
        validate_number(
            generator.capacity_mw,
            f"Capacity for {generator.name}",
        )
        validate_number(
            generator.marginal_cost_per_mwh,
            f"Marginal cost for {generator.name}",
        )

        if generator.capacity_mw < 0:
            raise ValueError(f"Capacity for {generator.name} must be nonnegative.")
    # Sort generators by marginal cost
    sorted_generators = sorted(generators, key=lambda g: g.marginal_cost_per_mwh)

    # Include every generator's dispatch in the result, even if they are not dispatched
    dispatch_mw = {generator.name: 0.0 for generator in sorted_generators}
    remaining_demand_mw = demand_mw
    clearing_price_per_mwh = None
    operating_profit_eur: dict[str, float] | None

    # Dispatch offers until demand is met or all generators are dispatched
    for generator in sorted_generators:
        if remaining_demand_mw <= 0:
            break

        allocated_mw = min(generator.capacity_mw, remaining_demand_mw)
        dispatch_mw[generator.name] = allocated_mw
        remaining_demand_mw -= allocated_mw

        if allocated_mw > 0:
            clearing_price_per_mwh = generator.marginal_cost_per_mwh

    # Calculate profits using dispatched energy and the uniform model price.
    if demand_mw == 0:
        clearing_price_per_mwh = None
        operating_profit_eur = {generator.name: 0.0 for generator in sorted_generators}

    elif clearing_price_per_mwh is None:
        operating_profit_eur = None
    else:
        # The same pricing policy applies to served demand and shortages.
        operating_profit_eur = {
            generator.name: (
                dispatch_mw[generator.name]
                * (clearing_price_per_mwh - generator.marginal_cost_per_mwh)
                * duration_hours
            )
            if dispatch_mw[generator.name] > 0
            else 0.0
            for generator in sorted_generators
        }

    # Power is independent of duration; energy equals power times hours.
    cleared_volume_mw = sum(dispatch_mw.values(), 0.0)
    cleared_energy_mwh = cleared_volume_mw * duration_hours
    unmet_demand_mw = max(0.0, demand_mw - cleared_volume_mw)
    unmet_energy_mwh = unmet_demand_mw * duration_hours

    return MarketResult(
        dispatch_mw=dispatch_mw,
        clearing_price_per_mwh=clearing_price_per_mwh,
        cleared_volume_mw=cleared_volume_mw,
        cleared_energy_mwh=cleared_energy_mwh,
        unmet_demand_mw=unmet_demand_mw,
        unmet_energy_mwh=unmet_energy_mwh,
        operating_profit_eur=operating_profit_eur,
    )
