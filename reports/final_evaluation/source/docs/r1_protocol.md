# R1 forecasting protocol

Status: frozen before first model fit
Experiment: r1_hourly_2023_v1
Freeze date: 2026-09-30

Matching configuration: `configs/r1.yaml` (paths are relative to the project root).
This document defines the experiment. Seasonal baselines and the single-alpha
Ridge pipeline are implemented; config loading and validation selection remain
planned. Preserve both files in version control before the first
fit. A changed rule or snapshot requires a new experiment identifier and record.

## Question

How does Ridge compare with previous-day and previous-week price
baselines on a small DE-LU hourly historical dataset?

This experiment demonstrates the workflow. It does not establish
general forecasting superiority.

## Data

- Zone: DE-LU
- Series: day-ahead electricity price
- Unit: EUR/MWh
- Resolution: hourly
- Delivery calendar: Europe/Berlin
- Stored interval timestamps: UTC
- Period: 2023-01-01 through 2023-04-01, inclusive
- Source: Energy-Charts
- Raw file: data/raw/energy_charts/DE-LU/2023-01-01_2023-04-01.json
- Raw SHA-256: 3785530A824163552BE3D646D2C70F43BD08BEB70E8E077C5E58EAD4C88896F7
- Processed file: data/processed/energy_charts/DE-LU/2023-01-01_2023-04-01.parquet
- Processed SHA-256: 9D67B2A91539175691AE312CE5E618D82AAFFCD3E9B384CCAC846F9CCDD1A280
- Quality report: reports/quality/DE-LU/2023-01-01_2023-04-01.period.json

The recorded quality report passes with 2,183 expected and observed hourly
intervals over 91 delivery days. Both SHA-256 values were checked against the
saved files on 2026-09-30. Hash comparisons are case-insensitive.

Historical publication times and revisions are unverified.
This is a latest-vintage historical benchmark, not exact
operational replay.

## Forecast timing

For delivery day D, issue all predictions at 11:00 Europe/Berlin
on D-1. Store the corresponding UTC origin with every prediction.

Assume the complete D-1 price curve is usable at this origin.
This assumption also applies to training labels. Historical
availability is not verified.

No target-day D prices may enter its features or model fitting.

## Features

- Previous local day's corresponding hourly price
- Previous local week's corresponding hourly price
- Local delivery hour
- Local weekday
- Repeated-hour occurrence

No actual load, generation, weather, or target-day prices.

Standardize the two numeric lag features with means and population standard
deviations fitted on the current training partition only. Use scale 1 for a
constant feature. One-hot encode calendar features using fixed categories:
hours 0-23, weekdays 0-6 (Monday = 0), and repeated-hour occurrence 0 or 1.
Occurrence 0 denotes an ordinary hour or the first repeated hour; occurrence 1
denotes the second repeated hour, ordered by UTC start. Keep all one-hot columns;
do not scale them. Fit Ridge with an intercept. Missing or non-finite price
features cause an explicit failure; do not impute them.

## Historical-curve alignment

Both baselines and Ridge's corresponding lag features use the same rules:

- Match D-1 or D-7 by local delivery hour and repeated-hour occurrence, not by
  shifting a fixed number of rows.
- If an occurrence is absent, use the available occurrence of the same hour.
- If the entire hour is absent because of DST, use the mean of that source
  day's complete observed curve. Record every substitution.
- A source day with its correct 23/24/25-hour calendar is complete. Missing
  expected records, duplicate/conflicting records, or an entirely absent source
  curve cause an explicit prediction failure, not a DST substitution.
- Never use target-day prices to repair inputs, or fill evaluation targets.

## Models

1. Previous-day price curve
2. Previous-week price curve
3. Ridge regression with alpha in [0.1, 1, 10, 100]

## Evaluation

All boundaries are inclusive Europe/Berlin delivery dates. Keep all intervals
of a delivery day together; never randomly split rows.

| Partition | First day | Last day | Purpose |
| --- | --- | --- | --- |
| Warm-up | 2023-01-01 | 2023-01-07 | Supply lags; not fitted or scored as targets |
| Initial training | 2023-01-08 | 2023-02-18 | Initial model/preprocessing fitting |
| Validation 1 | 2023-02-19 | 2023-02-25 | First selection block |
| Validation 2 | 2023-02-26 | 2023-03-04 | Second selection block |
| Validation 3 | 2023-03-05 | 2023-03-11 | Third selection block |
| Final evaluation | 2023-03-12 | 2023-04-01 | Descriptive comparison after selection |

### Fitting schedule and information boundary

For every alpha, refit preprocessing and Ridge before each validation block.
Training always starts on January 8 and ends the day before that block: February
18, February 25, and March 4 respectively. No validation-block targets enter its
model fit. Training labels follow the same assumed price-curve availability
rule as features; this is not a claim of verified historical publication.

Reconstruct every training row using its own D-1 forecast origin. Keep fitted
coefficients and preprocessing fixed inside each validation block. Daily lag
inputs update under the declared information rule.

After selection, fit the selected Ridge alpha once on January 8 through March
11. Keep coefficients and preprocessing fixed for March 12 through April 1.
Earlier evaluation-day prices may enter later daily lags under the same
assumption, but may not trigger refitting or retuning. Do not inspect final
evaluation scores until model-selection decisions are frozen.

### Metrics and selection

For each interval, error = prediction - actual and weight = duration in hours:

```text
MAE  = sum(weight * abs(error)) / sum(weight)
RMSE = sqrt(sum(weight * error**2) / sum(weight))
bias = sum(weight * error) / sum(weight)
```

All three metrics are in EUR/MWh. MAE is primary; RMSE and bias are secondary.
Use no MAPE. For selection, pool validation intervals across all three blocks
rather than averaging block RMSEs or averaging model ranks.

- Choose alpha from 0.1, 1, 10, 100 by lowest pooled duration-weighted validation
  MAE. An exact alpha tie chooses the larger alpha; do not expand the grid after
  inspecting scores.
- Choose the reference seasonal baseline by the same pooled validation MAE.
  Prefer previous-day if its MAE is no more than 1.01 times the best seasonal
  MAE. If the best MAE is zero, only another zero is a tie.
- Freeze alpha and the seasonal reference before final evaluation. Report both
  baselines and selected Ridge regardless of which is best.
- Report Ridge skill as 1 - MAE_Ridge / MAE_reference on common final intervals;
  mark it undefined when reference MAE is zero.

### Failures and reporting

Compare models on identical successful target intervals and show planned target
counts, successful predictions, duration coverage, common-interval counts,
prediction failures, and DST substitutions per model. A zero common denominator
produces undefined metrics, not zero error. During alpha selection use the same
common target set across candidates. Do not select or release a result with
unexplained prediction failures; investigate and record them without silently
dropping difficult intervals or adding an unregistered fallback.

Save predictions with model ID, forecast origin, delivery interval, lag-source
identity, substitution flags, and failure reasons. Save actual values separately
until scoring. Publish overall metrics and breakdowns by delivery day, month,
local hour, negative actual prices, and high actual prices, with group counts.
Empty groups have undefined metrics.

Freeze the high-price threshold at the 95th percentile of initial training
targets (January 8-February 18), using linear interpolation between sorted
values at index (n - 1) * 0.95. High-price events are strictly above this
threshold; negative-price events are strictly below zero. Do not recompute the
threshold from validation or final evaluation prices.

Retain the resolved configuration, snapshot hashes, source revision, dependency
lock hash, model/preprocessing settings, candidate scores, and runtime with the
results. Require repeat metrics within 1e-6 EUR/MWh in the locked environment.
Report descriptive comparisons only; R1 does not require Ridge to win and does
not support broad superiority or statistical-significance claims.

## Limitations

Short historical period, hourly scope, unknown historical vintages,
simple price/calendar features, and a simplified refit schedule.
