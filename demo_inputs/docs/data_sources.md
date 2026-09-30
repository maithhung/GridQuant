# Electricity-price data source

Updated: 2026-09-30 (Session 4 wrap-up). Current adapter: Energy-Charts,
DE-LU day-ahead prices. External source-check statements below retain their
Session 3 context; no fresh provider-policy audit was performed for this wrap-up.

## Request contract

- Provider: Energy-Charts (Fraunhofer ISE).
- Endpoint: `https://api.energy-charts.info/v2/price`.
- Parameters: `bzn=DE-LU`, `start=YYYY-MM-DD`, `end=YYYY-MM-DD`.
- Daily start/end strings select inclusive local delivery dates. Use the same
  date for both parameters to request one day.
- Public sample requests succeeded without credentials.
- The implemented fetch function uses one request with a 30-second socket
  timeout and returns bytes. HTTP and connection errors propagate without retry.

The [official API specification](https://api.energy-charts.info/openapi.json)
documents date semantics and rate limits. At the session's source check, price
requests were limited to two per minute with a burst of two, potentially lower
under load. Honor HTTP 429/Retry-After in future retry support; do not repeatedly
rerun failed requests. Cache reuse currently avoids repeat downloads.

## Response and interpretation

The response contains metadata plus a `data` array. Each record has `timestamp`
and `values.day_ahead_price`. Observed metadata includes endpoint `price`, zone
`DE-LU`, timezone `Europe/Berlin`, and unit `EUR / MWh`.

Timestamp offsets identify interval starts. The parser converts each start to
UTC and adds `interval_minutes` to obtain the exclusive end: `[start, end)`.
Native hourly and 15-minute durations are retained. No aggregation, interpolation,
or resampling is performed. Negative prices are valid; missing/null/non-finite
prices fail rather than becoming zero.

`PriceInterval` contains `delivery_start_utc`, `delivery_end_utc`,
`price_eur_per_mwh`, and `bidding_zone`. It represents a market price per unit of
energy, not a household tariff or a total payment.

The parser validates required structures/values and endpoint identity. It does
not require `schema_version == "2.0"`; the version present in saved responses is
descriptive metadata. A valid empty list returns an empty result. Global timing
consistency and all metadata relationships are not yet enforced by the parser.
Session 4 adds a separate one-day start-coverage checker; it does not validate
interval ends, ordering, or conflicting prices.

## Provenance and local storage

Samples are saved under:

```text
data/raw/energy_charts/DE-LU/<start>_<end>.json
data/raw/energy_charts/DE-LU/<start>_<end>.manifest.json
```

The manifest records `source`, `endpoint`, a copy of `parameters`,
`retrieved_at_utc`, `raw_sha256`, and `license`. Hashes identify original bytes.
`build_manifest` requires an offset-aware retrieval time and normalizes it to UTC.
`save_response` verifies the hash, serializes metadata, and refuses to overwrite
either existing file. The practice script checks endpoint, parameters, and hash
before loading cached data.

Sequential writes are not an atomic pair. Refresh, revisions, automatic recovery,
and a reusable raw-response loading helper are intentionally deferred. A valid hash establishes
byte integrity against the manifest, not source accuracy or historical availability.

## Attribution and evidence

The saved DE-LU responses state CC BY 4.0 with attribution
**Bundesnetzagentur | SMARD.de**. Acquisition is through Energy-Charts.info.
Preserve the returned license and attribution when sharing these samples; check
each dataset's terms rather than assuming all zones share the same license.
See [SMARD data use](https://www.smard.de/home/datennutzung) and the
[CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).

Original response bytes are preserved. Conversion to UTC and coverage summaries
are GridQuant transformations. The three historical samples contain 24, 23, and
25 hourly intervals respectively; see the
[coverage report](../reports/historical_sample_coverage.md). A fourth saved sample
for 2026-09-26 contains 96 quarter-hourly records and supports the practice demo.

These downloads are retrieved historical values, not archived auction-time
vintages. Neither API generation time nor GridQuant retrieval time proves when a
historical value first became available.

## Session 4 storage and quality contract

Normalized Parquet snapshots and JSON/Markdown reports are implemented for all
four saved samples. See the [data contract](data_contract.md) for types, embedded
metadata, output paths, replay behavior, and validation boundaries. The original
responses and manifests remain the evidence for source attribution and requests.

## Historical availability decision, 2026-09-30

| Question | Current evidence and conclusion |
| --- | --- |
| Which bytes were retrieved? | Raw response and matching SHA-256 in the saved manifest identify each snapshot. |
| When did GridQuant retrieve them? | The manifest records retrieval time; replay preserves it. |
| When was each exact historical value published? | Not established; source_publication_date remains null. |
| Can past values change, and under what policy? | Provider revision policy has not been verified in this session. |
| Can older versions be recovered? | Not established; no historical vintage archive has been verified. |

The evidence is the local raw/manifest pairs described above and their linked
quality reports. The existing API specification reference documents the source
contract, not a verified historical availability guarantee for these snapshots.
This is an explicit evidence gap, not a finding that the provider has no archives.

**Decision:** use a latest-vintage historical benchmark for Session 5 unless
further evidence supports historical replay. Here latest-vintage means the
historical snapshot retrieved and frozen locally, not a promise that it remains
the provider's newest revision. Keep source_publication_date and source_revision
null, and availability_evidence unknown. This limitation applies to lagged prices,
training labels, and any future features.

The user chose to defer availability.py. No eligibility filtering is implemented
or required for closing this learning session. Revisit it when a forecasting
workflow needs to select versions demonstrably available at each issuance time.
