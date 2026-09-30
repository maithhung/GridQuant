import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from gridquant.data.normalized import load_dataset
from gridquant.models.ridge import fit_ridge, forecast_ridge

dataset = load_dataset(
    Path("data/processed/energy_charts/DE-LU/2023-01-01_2023-04-01.parquet")
)

alphas = (0.1, 1.0, 10.0, 100.0)
training_start = date(2023, 1, 8)

blocks = (
    (date(2023, 2, 19), date(2023, 2, 25)),
    (date(2023, 2, 26), date(2023, 3, 4)),
    (date(2023, 3, 5), date(2023, 3, 11)),
)

berlin = ZoneInfo("Europe/Berlin")

actual_by_start = {
    row.delivery_start_utc: row.price_eur_per_mwh
    for row in dataset.intervals
    if date(2023, 2, 19)
    <= row.delivery_start_utc.astimezone(berlin).date()
    <= date(2023, 3, 11)
}

results: list[dict[str, object]] = []
pooled_mae_by_alpha: dict[float, float] = {}

for alpha in alphas:
    total_absolute_error = 0.0
    total_hours = 0.0
    total_predictions = 0

    for block_number, (block_start, block_end) in enumerate(blocks, start=1):
        training_end = block_start - timedelta(days=1)

        model = fit_ridge(
            dataset,
            training_start,
            training_end,
            alpha=alpha,
        )

        block_absolute_error = 0.0
        block_hours = 0.0
        block_predictions = 0

        delivery_date = block_start

        while delivery_date <= block_end:
            predictions = forecast_ridge(model, dataset, delivery_date)

            for prediction in predictions:
                if prediction.failure_reason is not None:
                    raise ValueError(
                        f"alpha={alpha}, target="
                        f"{prediction.delivery_start_utc}: "
                        f"{prediction.failure_reason}"
                    )

                predicted = prediction.prediction_eur_per_mwh
                if predicted is None:
                    raise ValueError("Prediction is missing without a failure reason.")

                actual = actual_by_start[prediction.delivery_start_utc]
                duration_hours = (
                    prediction.delivery_end_utc - prediction.delivery_start_utc
                ).total_seconds() / 3600

                block_absolute_error += duration_hours * abs(predicted - actual)
                block_hours += duration_hours
                block_predictions += 1

            delivery_date += timedelta(days=1)

        if block_predictions != 168:
            raise ValueError(
                f"Block {block_number}: expected 168 predictions, "
                f"got {block_predictions}."
            )

        block_mae = block_absolute_error / block_hours

        results.append(
            {
                "alpha": alpha,
                "block": block_number,
                "training_end": training_end.isoformat(),
                "validation_start": block_start.isoformat(),
                "validation_end": block_end.isoformat(),
                "predictions": block_predictions,
                "mae_eur_per_mwh": block_mae,
            }
        )

        total_absolute_error += block_absolute_error
        total_hours += block_hours
        total_predictions += block_predictions

    if total_predictions != 504:
        raise ValueError("Expected 504 validation predictions per alpha.")

    pooled_mae_by_alpha[alpha] = total_absolute_error / total_hours

best_alpha = min(
    alphas,
    key=lambda alpha: (pooled_mae_by_alpha[alpha], -alpha),
)

for alpha in alphas:
    print(f"alpha={alpha:6g}  pooled MAE={pooled_mae_by_alpha[alpha]:.6f} EUR/MWh")

print(f"Selected alpha: {best_alpha}")

output = Path("reports/ridge_validation.json")

document = {
    "experiment_id": "r1_hourly_2023_v1",
    "blocks": results,
    "pooled_mae_by_alpha": {
        str(alpha): score for alpha, score in pooled_mae_by_alpha.items()
    },
    "selected_alpha": best_alpha,
}

output.parent.mkdir(parents=True, exist_ok=True)
with output.open("x", encoding="utf-8") as file:
    json.dump(document, file, indent=2, allow_nan=False)
    file.write("\n")
