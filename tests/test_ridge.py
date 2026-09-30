from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pytest

from gridquant.data.models import DatasetMetadata, PriceDataset, PriceInterval
from gridquant.models.ridge import build_ridge_features, fit_ridge, forecast_ridge


def dataset_fixture(*, constant: bool = False) -> PriceDataset:
    start = datetime(2022, 12, 31, 23, tzinfo=UTC)
    return PriceDataset(
        series_id="day_ahead_price",
        metadata=DatasetMetadata(
            source="synthetic",
            source_document_id="ridge-test",
            raw_sha256="0" * 64,
            retrieved_at_utc=datetime(2026, 9, 30, tzinfo=UTC),
        ),
        intervals=tuple(
            PriceInterval(
                start + timedelta(hours=i),
                start + timedelta(hours=i + 1),
                -5.0 if constant else float((i % 24) - 10 + (i // 24) * 2),
                "DE-LU",
            )
            for i in range(24 * 24)
        ),
    )


def test_feature_values_are_aligned_and_exclude_target() -> None:
    dataset = dataset_fixture()
    row = build_ridge_features(dataset, date(2023, 1, 8))[14]
    assert row.values() == [16.0, 4.0, 14.0, 6.0, 0.0]
    assert row.previous_day.source_delivery_date == date(2023, 1, 7)
    assert row.previous_week.source_delivery_date == date(2023, 1, 1)
    assert row.failure_reason is None


def test_constant_prices_predict_constant_with_safe_scaling() -> None:
    dataset = dataset_fixture(constant=True)
    model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14))
    result = forecast_ridge(model, dataset, date(2023, 1, 15))
    assert model.training_rows == 168
    assert len(result) == 24
    assert all(row.failure_reason is None for row in result)
    assert [row.prediction_eur_per_mwh for row in result] == pytest.approx([-5.0] * 24)
    scaler = model.pipeline.named_steps["preprocess"].named_transformers_["prices"]
    assert scaler.mean_ == pytest.approx([-5.0, -5.0])
    assert scaler.scale_ == pytest.approx([1.0, 1.0])
    assert result[0].features.previous_day.raw_sha256 == "0" * 64


def test_preprocessing_uses_only_training_features() -> None:
    dataset = dataset_fixture()
    model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14))
    train_values = np.array(
        [
            row.values()
            for offset in range(7)
            for row in build_ridge_features(
                dataset, date(2023, 1, 8) + timedelta(days=offset)
            )
        ]
    )
    preprocess = model.pipeline.named_steps["preprocess"]
    scaler = preprocess.named_transformers_["prices"]
    np.testing.assert_allclose(scaler.mean_, train_values[:, :2].mean(axis=0))
    np.testing.assert_allclose(scaler.var_, train_values[:, :2].var(axis=0))
    # Two scaled prices, 24 hours, seven weekdays, and two occurrence categories.
    assert preprocess.transform(train_values).shape == (168, 35)


def test_held_out_changes_cannot_change_fit_or_same_day_prediction() -> None:
    dataset = dataset_fixture()
    cutoff = datetime(2023, 1, 14, 23, tzinfo=UTC)
    changed = replace(
        dataset,
        intervals=tuple(
            replace(row, price_eur_per_mwh=float("nan"))
            if row.delivery_start_utc >= cutoff
            else row
            for row in dataset.intervals
        ),
    )
    trimmed = replace(
        dataset,
        intervals=tuple(
            row for row in dataset.intervals if row.delivery_start_utc < cutoff
        ),
    )
    original = fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14))
    expected = forecast_ridge(original, dataset, date(2023, 1, 15))
    before = original.pipeline.named_steps["ridge"].coef_.copy()
    for altered in (changed, trimmed):
        fitted = fit_ridge(altered, date(2023, 1, 8), date(2023, 1, 14))
        np.testing.assert_allclose(fitted.pipeline.named_steps["ridge"].coef_, before)
        left = fitted.pipeline.named_steps["preprocess"].named_transformers_["prices"]
        right = original.pipeline.named_steps["preprocess"].named_transformers_[
            "prices"
        ]
        np.testing.assert_array_equal(left.mean_, right.mean_)
        assert forecast_ridge(original, altered, date(2023, 1, 15)) == expected
    np.testing.assert_array_equal(original.pipeline.named_steps["ridge"].coef_, before)


def test_missing_training_lag_fails_fit() -> None:
    dataset = dataset_fixture()
    broken = replace(dataset, intervals=dataset.intervals[1:])
    with pytest.raises(ValueError, match="previous_week"):
        fit_ridge(broken, date(2023, 1, 8), date(2023, 1, 14))


def test_missing_training_target_fails_fit() -> None:
    dataset = dataset_fixture()
    broken = replace(
        dataset, intervals=dataset.intervals[:168] + dataset.intervals[169:]
    )
    with pytest.raises(ValueError, match="Training targets"):
        fit_ridge(broken, date(2023, 1, 8), date(2023, 1, 14))


def test_missing_prediction_lag_returns_full_failure_grid() -> None:
    dataset = dataset_fixture()
    model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14))
    broken = replace(
        dataset, intervals=dataset.intervals[:312] + dataset.intervals[313:]
    )
    result = forecast_ridge(model, broken, date(2023, 1, 15))
    assert len(result) == 24
    assert all(
        row.prediction_eur_per_mwh is None and row.failure_reason for row in result
    )


def test_forecast_rejects_training_overlap() -> None:
    dataset = dataset_fixture()
    model = fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14))
    with pytest.raises(ValueError, match="after the final training"):
        forecast_ridge(model, dataset, date(2023, 1, 14))


@pytest.mark.parametrize("alpha", [0.0, -1.0, 2.0, float("nan"), float("inf")])
def test_alpha_must_belong_to_frozen_grid(alpha: float) -> None:
    with pytest.raises(ValueError, match="alpha must be one of"):
        fit_ridge(dataset_fixture(), date(2023, 1, 8), date(2023, 1, 14), alpha=alpha)


def test_invalid_arguments_fail_before_fitting() -> None:
    dataset = dataset_fixture()
    with pytest.raises(TypeError, match="boolean"):
        fit_ridge(dataset, date(2023, 1, 8), date(2023, 1, 14), alpha=True)
    with pytest.raises(ValueError, match="must not precede"):
        fit_ridge(dataset, date(2023, 1, 14), date(2023, 1, 8))


def test_ridge_preserves_spring_calendar_and_substitution() -> None:
    original = dataset_fixture()
    shift = timedelta(days=70)  # January 1 -> March 12, crossing spring DST.
    dataset = replace(
        original,
        intervals=tuple(
            replace(
                row,
                delivery_start_utc=row.delivery_start_utc + shift,
                delivery_end_utc=row.delivery_end_utc + shift,
            )
            for row in original.intervals
        ),
    )
    model = fit_ridge(dataset, date(2023, 3, 19), date(2023, 3, 25))
    spring = forecast_ridge(model, dataset, date(2023, 3, 26))
    assert len(spring) == 23
    assert all(row.failure_reason is None for row in spring)
    following = forecast_ridge(model, dataset, date(2023, 3, 27))
    assert len(following) == 24
    assert following[2].features.previous_day.substitution == "source_day_mean"
    assert following[2].failure_reason is None
