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
        cleared_volume_mwh=120.0,
        delivered_volume_mwh=120.0,
        unmet_demand_mwh=0.0,
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
    expected_cleared_volume_mwh = total_capacity_mw * duration_hours

    result = clear_market(
        generators=generators,
        demand_mw=demand_mw,
        duration_hours=duration_hours,
    )

    # When demand exceeds supply, every generator dispatches its full capacity.
    assert result.dispatch_mw == pytest.approx(
        {generator.name: generator.capacity_mw for generator in generators}
    )
    assert result.cleared_volume_mwh == pytest.approx(expected_cleared_volume_mwh)
    assert result.delivered_volume_mwh == pytest.approx(expected_cleared_volume_mwh)
    assert result.unmet_demand_mwh == pytest.approx(
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
