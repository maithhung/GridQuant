import math

import pytest

from gridquant.evaluation import mae_skill, weighted_metrics


def test_hand_calculation_with_unequal_durations_and_negative_prices() -> None:
    # Errors 2 and -4; weights 1 and 3. MAE=14/4, MSE=52/4, bias=-10/4.
    result = weighted_metrics([-5.0, 0.0], [-3.0, -4.0], [1.0, 3.0])
    assert result.count == 2
    assert result.duration_hours == 4.0
    assert result.mae == 3.5
    assert result.rmse == pytest.approx(math.sqrt(13))
    assert result.bias == -2.5


def test_perfect_and_empty_groups() -> None:
    perfect = weighted_metrics([-1.0, 0.0, 5.0], [-1.0, 0.0, 5.0], [1.0] * 3)
    assert perfect.mae == perfect.rmse == perfect.bias == 0.0
    empty = weighted_metrics([], [], [])
    assert empty.count == 0
    assert empty.mae is empty.rmse is empty.bias is None
    assert mae_skill(0.0, 0.0) is None
    assert mae_skill(None, 2.0) is None
    assert mae_skill(3.0, 4.0) == 0.25
    assert mae_skill(5.0, 4.0) == -0.25


@pytest.mark.parametrize("weight", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_weights(weight: float) -> None:
    with pytest.raises(ValueError):
        weighted_metrics([1.0], [2.0], [weight])


def test_invalid_lengths_prices_and_types() -> None:
    with pytest.raises(ValueError, match="lengths"):
        weighted_metrics([1.0], [], [1.0])
    with pytest.raises(ValueError, match="finite"):
        weighted_metrics([float("nan")], [2.0], [1.0])
    with pytest.raises(TypeError, match="numeric"):
        weighted_metrics([True], [2.0], [1.0])
