# Price dataset and reporting contract

Implemented state: 2026-09-30. This describes the current learning workflow.

## Typed structures

| Structure | Fields and meaning |
| --- | --- |
| PriceInterval | UTC delivery start/end, price_eur_per_mwh, bidding_zone |
| DatasetMetadata | source, source_document_id, raw_sha256, retrieved_at_utc; nullable source_publication_date and source_revision; availability_evidence and nullable availability_note |
| PriceDataset | series_id, shared metadata, tuple of intervals, schema_version (currently 1) |

One dataset represents one raw source snapshot. source_document_id currently
references its local raw JSON path; the hash identifies its bytes. Endpoint,
request parameters, and licensing remain in the companion raw manifest.
Source zone spelling DE-LU is retained. Publication and retrieval timestamps are
distinct; unknown publication/revision values stay null. The evidence field
currently accepts available/unavailable/unknown; all saved samples use unknown.
These labels do not implement an availability policy.

Within a snapshot, the conceptual price identity is series, bidding zone, and
delivery start/end. Storage does not enforce uniqueness or resolve conflicts.
Across snapshots, retain provenance instead of silently replacing values.
Actuals, forecast issue times, and record-level vintages are future extensions.

The frozen dataclasses provide structure, not runtime enforcement of every
invariant. The source parser, storage layer, and coverage checker have separate
validation responsibilities; none alone constitutes full dataset validation.

### Parser exception contract

As of Session 5 Step 1 (2026-09-30), invalid structural types, non-integer or
boolean `interval_minutes`, non-text timestamps, and non-numeric/boolean prices
raise `TypeError`. Nonpositive integer durations, malformed or timezone-naive
timestamp strings, non-finite prices, and unsupported endpoint/zone/unit values
raise `ValueError`. Malformed JSON retains `json.JSONDecodeError` (a `ValueError`
subclass).

Compatibility change: wrong types for duration, timestamp, and price previously
raised `ValueError`; callers handling malformed source data should catch both
`TypeError` and `ValueError`. Accepted data, interval conversion, and price values
are unchanged.

## Storage

```text
data/raw/energy_charts/DE-LU/<start>_<end>.json
data/raw/energy_charts/DE-LU/<start>_<end>.manifest.json
data/processed/energy_charts/DE-LU/<start>_<end>.parquet
reports/quality/DE-LU/<start>_<end>.json
reports/quality/DE-LU/<start>_<end>.md
```

`save_dataset(path, dataset)` and `load_dataset(path)` live in data/normalized.py.
Parquet columns use UTC microsecond timestamps, float64 EUR/MWh prices, and
string bidding zones. Embedded GridQuant metadata stores provenance, series,
unit, dataset schema version 1, and normalization version 1. These internal
versions do not impose exact-version gating on upstream JSON.

Save/load preserves row order, negative prices, duplicates, and empty datasets.
Naive timestamps and non-finite prices are rejected by the writer. UTC conversion
preserves instants; it does not preserve the original timestamp's offset spelling.
The loader checks the expected Parquet schema and required metadata, but does not
re-read/hash the raw response or establish historical availability.

Saving equal content at an existing path is a no-op. Different content raises
FileExistsError; select a new path for revisions. Raw files are not changed by
normalized storage. Writes are not atomic and interrupted-file recovery is not
implemented. Parquet bytes need not be identical across PyArrow versions.

## Coverage and reports

`check_daily_coverage(dataset, delivery_date, interval_minutes)` constructs the
expected grid from Europe/Berlin local midnights converted to UTC. The caller
specifies the expected resolution independently of the records. tzdata supplies
timezone rules on Windows. One day and one resolution are supported per call.

Coverage is unique matching starts / expected starts. Duplicates and unexpected
starts never increase the numerator. Diagnostics contain sorted unique UTC
starts; duplicate count means distinct starts repeated, not excess row count.
Complete-start-grid requires no missing, duplicate, or unexpected starts.
An empty dataset reports zero coverage for the requested day.

`save_quality_reports(dataset, delivery_date, interval_minutes, json_path)`
computes coverage once and writes report-schema-version 1 JSON plus Markdown at
the same stem. Both include counts, diagnostics, source identity/hash, and scope.
Identical report bytes are reused; different outputs are refused. Writes are
sequential, and a rerun can create a missing companion if existing content matches.

Reports cover starts only: interval ends/durations, overlaps, conflicting prices,
ordering, zone consistency, and historical eligibility are not certified. The
parser handles individual input records; broader dataset checks remain deferred.
No interpolation, gap filling, aggregation, deduplication, or automatic repair is
performed. A complete grid is not evidence of a forecasting-ready dataset.

## Reproduction and next use

Run `uv run python json_practice.py` from the repository root for the saved
2026-09-26 example. With the raw/manifest pair present it verifies the request and
hash, assembles the dataset, writes/reuses Parquet, checks the round trip, and
writes/reuses both reports. Missing raw input triggers HTTP; uv's offline option
alone does not block application network calls. The practice script currently
expects one day and 15-minute resolution; hourly calls must supply 60 explicitly.

All four saved samples have normalized outputs and reports. They are isolated
workflow samples, not training history. See [availability limitations](data_sources.md)
before developing the planned latest-vintage Session 5 benchmark. Preserve raw
manifests and the stated attribution when distributing transformed data.
