"""R1 Ridge with seasonal lag alignment and training-only preprocessing.

Uses the latest-vintage assumption of seasonal.py, not verified vintage replay.
Selection across validation blocks belongs to the experiment runner; these
functions fit one alpha and never choose parameters from held-out targets.
"""

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.compose import ColumnTransformer  # type: ignore[import-untyped]
from sklearn.linear_model import Ridge  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]
from sklearn.preprocessing import (  # type: ignore[import-untyped]
    OneHotEncoder,
    StandardScaler,
)

from gridquant.data.models import PriceDataset
from gridquant.data.period_quality import check_hourly_period
from gridquant.models.seasonal import SeasonalPrediction, forecast_seasonal

BERLIN = ZoneInfo("Europe/Berlin")
R1_ALPHAS = (0.1, 1.0, 10.0, 100.0)


@dataclass(frozen=True)
class RidgeFeatures:
    """A target's inputs and audit trail, with no actual target price."""

    previous_day: SeasonalPrediction
    previous_week: SeasonalPrediction
    weekday: int

    @property
    def failure_reason(self) -> str | None:
        reasons = [
            f"{lag.model_id}: {lag.failure_reason}"
            for lag in (self.previous_day, self.previous_week)
            if lag.failure_reason is not None
        ]
        return "; ".join(reasons) if reasons else None

    def values(self) -> list[float]:
        """Numeric lags followed by hour, weekday, and repeated-hour occurrence."""
        day_price = self.previous_day.prediction_eur_per_mwh
        week_price = self.previous_week.prediction_eur_per_mwh
        if self.failure_reason or day_price is None or week_price is None:
            raise ValueError(self.failure_reason or "Missing lag price.")
        if not isfinite(day_price) or not isfinite(week_price):
            raise ValueError("Lag prices must be finite.")
        return [
            day_price,
            week_price,
            float(self.previous_day.local_hour),
            float(self.weekday),
            float(self.previous_day.repeated_hour_occurrence),
        ]


@dataclass(frozen=True)
class RidgeModel:
    """Fitted pipeline plus the exact training boundary and source identity."""

    pipeline: Pipeline
    alpha: float
    training_start: date
    training_end: date
    training_rows: int
    source_document_id: str
    raw_sha256: str


@dataclass(frozen=True)
class RidgePrediction:
    origin_utc: datetime
    delivery_start_utc: datetime
    delivery_end_utc: datetime
    prediction_eur_per_mwh: float | None
    features: RidgeFeatures
    failure_reason: str | None
    alpha: float
    training_end: date
    model_id: str = "ridge"
    evidence_track: str = "latest_vintage"


def build_ridge_features(
    dataset: PriceDataset, delivery_date: date
) -> tuple[RidgeFeatures, ...]:
    """Build a complete target-day feature grid without reading its actuals."""
    previous_day = forecast_seasonal(dataset, delivery_date, lag_days=1)
    previous_week = {
        row.delivery_start_utc: row
        for row in forecast_seasonal(dataset, delivery_date, lag_days=7)
    }
    if {row.delivery_start_utc for row in previous_day} != previous_week.keys():
        raise ValueError("Seasonal target grids differ.")
    return tuple(
        RidgeFeatures(
            previous_day=row,
            previous_week=previous_week[row.delivery_start_utc],
            weekday=row.delivery_start_utc.astimezone(BERLIN).weekday(),
        )
        for row in previous_day
    )


def fit_ridge(
    dataset: PriceDataset,
    training_start: date,
    training_end: date,
    *,
    alpha: float = 1.0,
) -> RidgeModel:
    """Fit one frozen-grid alpha on inclusive local training target dates.

    Training labels are joined only after features are built at each row's own
    origin. Source curves through the prior day are assumed usable. Invalid
    labels or missing lag features fail the fit rather than silently dropping rows.
    """
    for boundary in (training_start, training_end):
        if not isinstance(boundary, date) or isinstance(boundary, datetime):
            raise TypeError("Training boundaries must be dates, not datetimes.")
    if training_end < training_start:
        raise ValueError("training_end must not precede training_start.")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
        raise TypeError("alpha must be numeric, not a boolean.")
    if not isfinite(alpha) or alpha not in R1_ALPHAS:
        raise ValueError(f"alpha must be one of {R1_ALPHAS}.")

    target_rows = []
    for row in dataset.intervals:
        start = row.delivery_start_utc
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("Input starts must include a UTC offset.")
        if training_start <= start.astimezone(BERLIN).date() <= training_end:
            target_rows.append(row)
    quality = check_hourly_period(
        replace(dataset, intervals=tuple(target_rows)), training_start, training_end
    )
    if not quality.passed:
        raise ValueError("Training targets must form valid complete hourly days.")

    features: list[RidgeFeatures] = []
    day = training_start
    while day <= training_end:
        features.extend(build_ridge_features(dataset, day))
        day += timedelta(days=1)
    matrix = np.asarray([row.values() for row in features], dtype=float)
    targets = {
        row.delivery_start_utc.astimezone(UTC): row.price_eur_per_mwh
        for row in target_rows
    }
    labels = [targets[row.previous_day.delivery_start_utc] for row in features]

    preprocess = ColumnTransformer(
        [
            ("prices", StandardScaler(), [0, 1]),
            (
                "calendar",
                OneHotEncoder(
                    categories=[list(range(24)), list(range(7)), [0, 1]],
                    drop=None,
                    handle_unknown="error",
                    sparse_output=False,
                ),
                [2, 3, 4],
            ),
        ],
        remainder="drop",
    )
    pipeline = Pipeline(
        [
            ("preprocess", preprocess),
            ("ridge", Ridge(alpha=float(alpha), fit_intercept=True, solver="svd")),
        ]
    )
    pipeline.fit(matrix, labels)
    return RidgeModel(
        pipeline=pipeline,
        alpha=float(alpha),
        training_start=training_start,
        training_end=training_end,
        training_rows=len(features),
        source_document_id=dataset.metadata.source_document_id,
        raw_sha256=dataset.metadata.raw_sha256,
    )


def forecast_ridge(
    model: RidgeModel, dataset: PriceDataset, delivery_date: date
) -> tuple[RidgePrediction, ...]:
    """Predict a subsequent local day without refitting or reading its labels."""
    if not isinstance(delivery_date, date) or isinstance(delivery_date, datetime):
        raise TypeError("delivery_date must be a date, not a datetime.")
    if delivery_date <= model.training_end:
        raise ValueError("Forecast day must be after the final training target day.")
    features = build_ridge_features(dataset, delivery_date)
    results: list[RidgePrediction] = []
    for row in features:
        failure = row.failure_reason
        prediction: float | None = None
        if failure is None:
            prediction = float(
                model.pipeline.predict(np.asarray([row.values()], dtype=float))[0]
            )
            if not isfinite(prediction):
                failure = "Ridge produced a non-finite prediction."
                prediction = None
        target = row.previous_day
        results.append(
            RidgePrediction(
                origin_utc=target.origin_utc,
                delivery_start_utc=target.delivery_start_utc,
                delivery_end_utc=target.delivery_end_utc,
                prediction_eur_per_mwh=prediction,
                features=row,
                failure_reason=failure,
                alpha=model.alpha,
                training_end=model.training_end,
            )
        )
    return tuple(results)
