# Historical price sample verification

Three DE-LU samples were acquired from Energy-Charts `/v2/price` and replayed
offline using the existing parser. Exact acquisition times, request parameters,
licenses, and SHA-256 hashes are stored beside each original JSON response in
`data/raw/energy_charts/DE-LU/`.

| Local delivery day | Resolution | Intervals | UTC start (inclusive) | UTC end (exclusive) | Result |
| --- | --- | --- | --- | --- | --- |
| 2023-02-15 | 60 minutes | 24 | 2023-02-14 23:00 | 2023-02-15 23:00 | PASS |
| 2023-03-26 | 60 minutes | 23 | 2023-03-25 23:00 | 2023-03-26 22:00 | PASS |
| 2023-10-29 | 60 minutes | 25 | 2023-10-28 22:00 | 2023-10-29 23:00 | PASS |

All samples match their full expected UTC interval grids: no missing, duplicate,
out-of-range, or out-of-order interval starts. Interval ends and native durations
match. Manifest request identity and raw hashes pass, and repeated parsing gives
identical records. The metadata reports schema 2.0, endpoint price, Europe/Berlin,
and PT1H/60-minute resolution. This is sample verification, not an audit of the
entire historical dataset or proof of historical publication availability.

The Python environment lacks the `tzdata` package, so expected local-midnight
boundaries were independently derived from Windows' Berlin timezone rules
(`W. Europe Standard Time`). The saved reference boundaries are in
`historical_sample_calendars.json`; detailed results are in
`historical_sample_coverage.json`. No fixed 24-hour assumption was used.

Source: [Energy-Charts API](https://api.energy-charts.info/).
Returned data license: CC BY 4.0, attribution **Bundesnetzagentur | SMARD.de**.
The raw price values were not transformed; derived UTC coverage is reported here.

Local offline verification command, from the repository root:

```powershell
uv run --offline python docs/local/verify_historical_samples.py
```

The local audit script defaults to reading saved files only. Its optional
`--fetch` switch downloads missing samples; it is a one-off audit helper, not the
planned reusable client with retry and revision-storage support.
