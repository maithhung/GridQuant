import pytest

from gridquant.merit_order import GeneratorOffer, MarketResult, clear_market


def test_clear_market_worked_example() -> None:
    # Define a set of generator offers
    generators = [
        GeneratorOffer(name="A", capacity_mw=50.0, marginal_cost_per_mwh=10.0),
        GeneratorOffer(name="B", capacity_mw=100.0, marginal_cost_per_mwh=40.0),
        GeneratorOffer(name="C", capacity_mw=80.0, marginal_cost_per_mwh=70.0),
    ]

    # Test case 1: call function clear_market with demand of 120 MW and duration of 1 hour
    result = clear_market(generators=generators, demand_mw=120.0, duration_hours=1.0)

    # Assert: Compare actual and expected results
    expected_result = MarketResult(
        dispatch_mw={"A": 50.0, "B": 70.0, "C": 0.0},
        clearing_price_per_mwh=40.0,
        cleared_volume_mw=120.0,
        cleared_energy_mwh=120.0,
        unmet_demand_mw=0.0,
        unmet_energy_mwh=0.0,
        operating_profit_eur={
            "A": 1500.0,  # 50 MW * (40 - 10) eur/MWh * 1 hour
            "B": 0.0,  # 70 MW * (40 - 40) eur/MWh * 1 hour
            "C": 0.0,  # Not dispatched
        },
    )
    assert result == pytest.approx(expected_result, rel=1e-6)


def test_negative_demand_is_rejected() -> None:
    generators = [
        GeneratorOffer(name="A", capacity_mw=50.0, marginal_cost_per_mwh=10.0),
    ]

    with pytest.raises(ValueError):
        clear_market(generators=generators, demand_mw=-1.0)


def test_demand_exceeds_total_capacity() -> None:
    generators = [
        GeneratorOffer(name="A", capacity_mw=50.0, marginal_cost_per_mwh=10.0),
        GeneratorOffer(name="B", capacity_mw=100.0, marginal_cost_per_mwh=40.0),
        GeneratorOffer(name="C", capacity_mw=80.0, marginal_cost_per_mwh=70.0),
    ]

    demand_mw = 300.0
    duration_hours = 0.5
    total_capacity_mw = sum(generator.capacity_mw for generator in generators)
    expected_cleared_energy_mwh = total_capacity_mw * duration_hours

    result = clear_market(
        generators=generators,
        demand_mw=demand_mw,
        duration_hours=duration_hours,
    )

    # When demand exceeds supply, every generator dispatches its full capacity.
    assert result.dispatch_mw == pytest.approx(
        {generator.name: generator.capacity_mw for generator in generators}
    )
    assert result.cleared_volume_mw == pytest.approx(total_capacity_mw)
    assert result.cleared_energy_mwh == pytest.approx(expected_cleared_energy_mwh)
    assert result.unmet_demand_mw == pytest.approx(demand_mw - total_capacity_mw)
    assert result.unmet_energy_mwh == pytest.approx(
        (demand_mw - total_capacity_mw) * duration_hours
    )
    # During shortages, prices are set by the highest marginal cost among dispatched generators.
    assert result.clearing_price_per_mwh == pytest.approx(
        70.0
    )  # The highest marginal cost among dispatched generators
    assert result.operating_profit_eur == pytest.approx(
        {
            "A": 50.0 * (70.0 - 10.0) * duration_hours,
            "B": 100.0 * (70.0 - 40.0) * duration_hours,
            "C": 80.0 * (70.0 - 70.0) * duration_hours,
        }
    )


def test_identical_duplicate_names_are_rejected() -> None:
    generators = [
        GeneratorOffer("A", 50.0, 10.0),
        GeneratorOffer("A", 50.0, 10.0),
    ]

    with pytest.raises(ValueError, match="Duplicate generator name"):
        clear_market(generators, demand_mw=75.0)


@pytest.mark.parametrize("duration_hours", [0.25, 0.5, 1.0, 2.0])
@pytest.mark.parametrize(
    "demand_mw, expected_power, expected_unmet, expected_price, hourly_profits",
    [
        (120.0, 120.0, 0.0, 40.0, {"A": 1500.0, "B": 0.0, "C": 0.0}),
        (300.0, 230.0, 70.0, 70.0, {"A": 3000.0, "B": 3000.0, "C": 0.0}),
    ],
)
def test_power_energy_and_money_units(
    duration_hours: float,
    demand_mw: float,
    expected_power: float,
    expected_unmet: float,
    expected_price: float,
    hourly_profits: dict[str, float],
) -> None:
    generators = [
        GeneratorOffer("A", 50.0, 10.0),
        GeneratorOffer("B", 100.0, 40.0),
        GeneratorOffer("C", 80.0, 70.0),
    ]
    result = clear_market(generators, demand_mw, duration_hours)

    assert result.cleared_volume_mw == pytest.approx(expected_power)
    assert sum(result.dispatch_mw.values()) == pytest.approx(expected_power)
    assert result.unmet_demand_mw == pytest.approx(expected_unmet)
    assert result.cleared_energy_mwh == pytest.approx(expected_power * duration_hours)
    assert result.unmet_energy_mwh == pytest.approx(expected_unmet * duration_hours)
    assert result.cleared_energy_mwh + result.unmet_energy_mwh == pytest.approx(
        demand_mw * duration_hours
    )
    assert result.clearing_price_per_mwh == pytest.approx(expected_price)
    assert result.operating_profit_eur == pytest.approx(
        {name: profit * duration_hours for name, profit in hourly_profits.items()}
    )


@pytest.mark.parametrize("demand_mw", [0.0, 20.0])
def test_no_dispatch_units(demand_mw: float) -> None:
    result = clear_market([GeneratorOffer("A", 0.0, 10.0)], demand_mw, 0.25)
    assert result.cleared_volume_mw == 0.0
    assert result.cleared_energy_mwh == 0.0
    assert result.unmet_demand_mw == demand_mw
    assert result.unmet_energy_mwh == demand_mw * 0.25
    assert result.clearing_price_per_mwh is None
    assert result.operating_profit_eur == ({"A": 0.0} if demand_mw == 0 else None)
