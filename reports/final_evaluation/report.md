# R1 final evaluation

Period: March 12-April 1, 2023 (Europe/Berlin).
Ridge alpha: 100. Seasonal reference: previous_day.
One final Ridge fit: January 8-March 11; 1512 rows. No refitting during evaluation.

| Model | MAE | RMSE | Bias | Successful / planned | DST substitutions |
| --- | ---: | ---: | ---: | ---: | ---: |
| previous_day | 28.695400 | 37.632581 | 2.184203 | 503 / 503 | 1 |
| previous_week | 41.537594 | 52.751187 | 11.021650 | 503 / 503 | 0 |
| ridge | 27.185979 | 36.674083 | 17.129161 | 503 / 503 | 1 |

Errors are duration-weighted, in EUR/MWh; bias is prediction minus actual.
Common scored intervals: 503. Coverage gate passed: True.
Ridge skill versus the frozen reference: 5.26%.
High-price threshold: 203.313000 EUR/MWh (initial training 95th percentile).

This is a short latest-vintage historical benchmark. Historical publication and revision
availability are unverified. Results are descriptive, with no significance or general-superiority claim.
The saved selections were not retuned after final scoring. Validation reports did not originally
record snapshot hashes; this run captures their bytes and the current verified dataset together.

See metrics.json for daily/month/hour/event breakdowns, predictions.json for interval errors
and lag provenance, model.json for fitted parameters, and manifest.json for source/output hashes.
