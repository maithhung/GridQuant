from dataclasses import dataclass


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
    cleared_volume_mwh: float  # in MWh
    delivered_volume_mwh: float  # in MWh
    unmet_demand_mwh: float  # in MWh
    operating_profit_eur: dict[str, float] | None


def clear_market(
    generators: list[GeneratorOffer],
    demand_mw: float,
    duration_hours: float = 1.0,
) -> MarketResult:
    """Clears the market based on the merit order of generator offers.

    Args:
        generators (list[GeneratorOffer]): List of generator offers sorted by marginal cost.
        demand_mw (float): Total demand in MW.
        duration_hours (float): Duration of the market clearing in hours.

    Returns:
        MarketResult: The result of the market dispatch.
    """
    # Check for generator name duplication
    for generator in generators:
        if generator.name in [g.name for g in generators if g != generator]:
            raise ValueError(f"Duplicate generator name found: {generator.name}")
    # Negative demand check
    if demand_mw < 0:
        raise ValueError("Demand must be nonnegative.")
    # Sort generators by marginal cost
    sorted_generators = sorted(generators, key=lambda g: g.marginal_cost_per_mwh)

    # Include every generator's dispatch in the result, even if they are not dispatched
    dispatch_mw = {generator.name: 0.0 for generator in sorted_generators}
    remaining_demand_mw = demand_mw
    clearing_price_per_mwh = None
    cleared_volume_mwh = 0.0
    delivered_volume_mwh = 0.0
    unmet_demand_mwh = 0.0
    operating_profit_eur = dict[str, float] | None

    # Dispatch offers until demand is met or all generators are dispatched
    for generator in sorted_generators:
        if remaining_demand_mw <= 0:
            break

        allocated_mw = min(generator.capacity_mw, remaining_demand_mw)
        dispatch_mw[generator.name] = allocated_mw
        remaining_demand_mw -= allocated_mw

        if allocated_mw > 0:
            clearing_price_per_mwh = generator.marginal_cost_per_mwh

    # Update cleared and delivered volumes
    if demand_mw == 0:
        clearing_price_per_mwh = None
        operating_profit_eur = {generator.name: 0.0 for generator in sorted_generators}

    elif remaining_demand_mw > 0:
        # Not all demand was met
        cleared_volume_mwh = demand_mw - remaining_demand_mw
        delivered_volume_mwh = cleared_volume_mwh
        operating_profit_eur = {
            generator.name: dispatch_mw[generator.name]
            * (clearing_price_per_mwh - generator.marginal_cost_per_mwh)
            * duration_hours
            for generator in sorted_generators
            if dispatch_mw[generator.name] > 0
        }

    else:
        # All demand was met
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

    # Cleared volume is the total dispatched volume in MWh
    cleared_volume_mwh = sum(dispatch_mw.values()) * duration_hours
    unmet_demand_mwh = max(
        0.0, (demand_mw - sum(dispatch_mw.values())) * duration_hours
    )
    delivered_volume_mwh = cleared_volume_mwh

    return MarketResult(
        dispatch_mw=dispatch_mw,
        clearing_price_per_mwh=clearing_price_per_mwh,
        cleared_volume_mwh=cleared_volume_mwh,
        delivered_volume_mwh=delivered_volume_mwh,
        unmet_demand_mwh=unmet_demand_mwh,
        operating_profit_eur=operating_profit_eur if operating_profit_eur else None,
    )
