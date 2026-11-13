# Raw data — sources & provenance

Files in this folder are **read-only inputs**. They are never edited; all preparation happens in
`src/data_prep.py`, which writes to `data/processed/`.

## 1. `prices.csv` — main dataset

| Field | Value |
|---|---|
| Title | Streaming Price Tracker — price change dataset (one row per price change) |
| Publisher | Streaming Price Tracker (streamingpricetracker.com) |
| URL | https://streamingpricetracker.com/data/prices.csv |
| Licence | **CC BY 4.0** — attribution to Streaming Price Tracker required |
| Accessed | 2026-11-13 (canonical copy from the site; identical to the group's earlier download for all `onDemand` rows — the only diffs are live-TV rows, which are out of scope) |
| Coverage | 2010-06-29 → 2026-09-23 (plus one Nov-2026 live-TV row) |
| Scope filter used in the project | `category == "onDemand"` and `service_name != "ESPN"` → 89 events, 20 plans, 8 services |
| Stated scope of the source | Standard monthly US list prices. Annual plans and promotional pricing excluded. "Hand-tracked and verified monthly by one person, with at least two sources behind every price." Per-entry source citations live on https://streamingpricetracker.com/history/ |

Fields: `service_key, service_name, category, plan_key, plan_label, discontinued, addon, effective_date, price_usd`

## 2. `prices.json` — same dataset in JSON form

| Field | Value |
|---|---|
| URL | https://streamingpricetracker.com/data/prices.json |
| Licence | CC BY 4.0 (same as above) |
| Used for | service brand colours (taken from its `color` fields, credited below) and plan `notes` (e.g. Netflix Basic wind-down dates) |

## 3. `CPIAUCSL.csv` — inflation data

| Field | Value |
|---|---|
| Series | CPIAUCSL — Consumer Price Index for All Urban Consumers: All Items, US city average, seasonally adjusted (index 1982-84 = 100) |
| Publisher | U.S. Bureau of Labor Statistics, via FRED, Federal Reserve Bank of St. Louis |
| URL | https://fred.stlouisfed.org/series/CPIAUCSL |
| Accessed | 2026-11-02 (monthly series, 1947-01 → 2026-09) |
| Role | Deflator for real prices (Q4) and the inflation baseline for the growth-vs-inflation scatter |

## 4. `streaming_service.csv` — cross-check dataset (not used in any chart)

| Field | Value |
|---|---|
| Title | Streaming Service Price History |
| Author | Takumi Watanabe (`webdevbadger`) |
| URL | https://www.kaggle.com/datasets/webdevbadger/streaming-service-prices |
| Licence | CC0: Public Domain |
| Coverage | 2011-07 → 2024-01, 10 services, monthly rows (777) |
| Stated scope | "All prices are for ad-free, lowest-cost monthly subscriptions. U.S. price. Lowest cost. No ads. No bundle." |
| Role | Independent validation of the main dataset — compared against it in `data/processed/validation_report.md` |

## Attribution statement (used in the dashboard footer)

> Price data: [Streaming Price Tracker](https://streamingpricetracker.com/), CC BY 4.0.
> Inflation data: U.S. Bureau of Labor Statistics (CPIAUCSL) via FRED.
> Cross-check dataset: "Streaming Service Price History" by Takumi Watanabe (Kaggle, CC0).
