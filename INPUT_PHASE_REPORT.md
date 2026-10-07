# Input Pipeline Pilot Report

## Experiment

- ID: `aapl-input-pilot-v1`
- Ticker: `AAPL`
- Dates: 2026-07-14, 2026-07-29, 2026-08-18
- Cutoff: 16:00 `America/New_York`
- Market lookback: 90 trading bars
- News lookback: 7 calendar days
- Polymarket: disabled

## Live source results

| Source | Result | Stored content |
|---|---|---|
| Yahoo Finance | Success | 90 eligible OHLCV bars and deterministic technical features per date |
| FRED/ALFRED | Success | Point-in-time observations for DFF, CPIAUCSL, UNRATE, DGS10, and T10Y2Y |
| SEC EDGAR | Success | Eight selected facts with start/end, duration, form, fiscal period, unit, filing date, accession ID, and XBRL concept source |
| Marketaux | Success | Complete news and ticker sentiment for all three retained pilot dates |
| Alpha Vantage | Fallback unavailable | The supplied account reports historical NEWS_SENTIMENT as a premium endpoint |
| Polymarket | Disabled | Excluded by research decision |

The Alpha Vantage failure is preserved in each snapshot's `source_meta`; current news was not substituted.

## Validated complete snapshot hashes

| Decision date | SHA-256 |
|---|---|
| 2026-07-14 | `a2cda138e8b3d4d3ce495e193ca3061c650bef4d727d0400eb0e419ca708b187` |
| 2026-07-29 | `17404d3265a9321d25c0964f4947a1f1aec51b1e4d221f8dbd74e106b4a5bea9` |
| 2026-08-18 | `be2ec238b4bde2ca437331b830f25d609a37ebcad68f413c06a1d06424e07325` |

## Verification

- Schema version `1.1.0` removes ambiguity between instant, quarterly, year-to-date, and annual SEC facts.
- 12 automated tests pass.
- Every persisted full snapshot passes point-in-time validation.
- Recomputed content hashes match stored hashes.
- Rebuilding all five snapshots entirely from cached inputs reproduces the hashes above.
- FRED observations include explicit units and real-time vintage dates.
- Technical features carry an explicit indicator-set version.
- Raw provider responses are cached separately from normalized snapshots.
- Credentials are loaded from the ignored local `.env` file.

## Remaining exit-gate issue

The three-date pilot is complete. Prices, news, macro, and fundamentals are required; the builder refuses to accept a snapshot missing any of them.
