"""Duration-weighted forecast metrics; empty groups have undefined scores."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum, isfinite, sqrt


@dataclass(frozen=True)
class ForecastMetrics:
    count: int
    duration_hours: float
    mae: float | None
    rmse: float | None
    bias: float | None


def weighted_metrics(
    actual: Sequence[float],
    predicted: Sequence[float],
    duration_hours: Sequence[float],
) -> ForecastMetrics:
    """Return EUR/MWh errors with bias defined as prediction minus actual."""
    if not len(actual) == len(predicted) == len(duration_hours):
        raise ValueError("Actual, predicted, and duration lengths must match.")
    for values in (actual, predicted, duration_hours):
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError("Metric inputs must be numeric, not booleans.")
            if not isfinite(value):
                raise ValueError("Metric inputs must be finite.")
    if any(hours <= 0 for hours in duration_hours):
        raise ValueError("Durations must be positive.")
    if not actual:
        return ForecastMetrics(0, 0.0, None, None, None)
    hours = fsum(duration_hours)
    errors = [
        forecast - observed
        for observed, forecast in zip(actual, predicted, strict=True)
    ]
    return ForecastMetrics(
        count=len(actual),
        duration_hours=hours,
        mae=fsum(
            w * abs(error) for w, error in zip(duration_hours, errors, strict=True)
        )
        / hours,
        rmse=sqrt(
            fsum(w * error**2 for w, error in zip(duration_hours, errors, strict=True))
            / hours
        ),
        bias=fsum(w * error for w, error in zip(duration_hours, errors, strict=True))
        / hours,
    )


def mae_skill(model_mae: float | None, reference_mae: float | None) -> float | None:
    """Undefined for missing scores or a perfect (zero-MAE) reference."""
    if model_mae is None or reference_mae is None or reference_mae == 0:
        return None
    return 1 - model_mae / reference_mae
