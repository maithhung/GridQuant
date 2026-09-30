import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from gridquant.data.normalized import load_dataset
from gridquant.models.seasonal import forecast_seasonal

dataset = load_dataset(
    Path("data/processed/energy_charts/DE-LU/2023-01-01_2023-04-01.parquet")
)

validation_start = date(2023, 2, 19)
validation_end = date(2023, 3, 11)
berlin = ZoneInfo("Europe/Berlin")

actual_by_start = {
    row.delivery_start_utc: row.price_eur_per_mwh
    for row in dataset.intervals
    if validation_start
    <= row.delivery_start_utc.astimezone(berlin).date()
    <= validation_end
}

if len(actual_by_start) != 504:
    raise ValueError("Expected 504 unique validation targets.")

scores: dict[str, float] = {}
counts: dict[str, int] = {}
substitution_counts: dict[str, int] = {}

for model_name, lag_days in (
    ("previous_day", 1),
    ("previous_week", 7),
):
    weighted_absolute_error = 0.0
    total_hours = 0.0
    predicted_starts = set()
    substitutions = 0

    delivery_date = validation_start

    while delivery_date <= validation_end:
        predictions = forecast_seasonal(
            dataset,
            delivery_date,
            lag_days=lag_days,
        )

        for prediction in predictions:
            if prediction.failure_reason is not None:
                raise ValueError(
                    f"{model_name}, {prediction.delivery_start_utc}: "
                    f"{prediction.failure_reason}"
                )

            predicted = prediction.prediction_eur_per_mwh
            if predicted is None:
                raise ValueError("Missing prediction.")

            start = prediction.delivery_start_utc
            if start in predicted_starts:
                raise ValueError(f"Duplicate prediction: {start}")

            actual = actual_by_start[start]
            duration_hours = (
                prediction.delivery_end_utc - prediction.delivery_start_utc
            ).total_seconds() / 3600

            weighted_absolute_error += duration_hours * abs(predicted - actual)
            total_hours += duration_hours
            predicted_starts.add(start)

            if prediction.substitution != "none":
                substitutions += 1

        delivery_date += timedelta(days=1)

    if predicted_starts != actual_by_start.keys():
        raise ValueError(f"{model_name}: prediction coverage differs from targets.")

    scores[model_name] = weighted_absolute_error / total_hours
    counts[model_name] = len(predicted_starts)
    substitution_counts[model_name] = substitutions

best_mae = min(scores.values())

if best_mae == 0.0:
    selected_reference = (
        "previous_day" if scores["previous_day"] == 0.0 else "previous_week"
    )
elif scores["previous_day"] <= 1.01 * best_mae:
    selected_reference = "previous_day"
else:
    selected_reference = "previous_week"

ridge_results = json.loads(
    Path("reports/ridge_validation.json").read_text(encoding="utf-8")
)

selected_alpha = ridge_results["selected_alpha"]
ridge_mae = ridge_results["pooled_mae_by_alpha"][str(selected_alpha)]

for model_name, mae in scores.items():
    print(f"{model_name:15s}: {mae:.6f} EUR/MWh")

print(f"Ridge alpha={selected_alpha:g}: {ridge_mae:.6f} EUR/MWh")
print(f"Selected seasonal reference: {selected_reference}")

document = {
    "experiment_id": "r1_hourly_2023_v1",
    "validation_start": validation_start.isoformat(),
    "validation_end": validation_end.isoformat(),
    "mae_eur_per_mwh": scores,
    "prediction_counts": counts,
    "substitution_counts": substitution_counts,
    "selected_reference": selected_reference,
    "selection_rule": "Prefer previous_day within 1% of best; exact ties at zero.",
}

output = Path("reports/seasonal_validation.json")
output.parent.mkdir(parents=True, exist_ok=True)

with output.open("x", encoding="utf-8") as file:
    json.dump(document, file, indent=2, allow_nan=False)
    file.write("\n")
