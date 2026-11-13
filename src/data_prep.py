"""Streamflation — data preparation pipeline.

Reads the raw sources in data/raw/ (never modified) and writes analysis-ready
tables to data/processed/. Every table consumed by the dashboard is produced
here, so the whole preparation step is reproducible with one command:

    python src/data_prep.py

Steps
-----
1.  Load and validate the Streaming Price Tracker event data.
2.  Scope: onDemand services, excluding ESPN (group decision — see README).
3.  Derive per-event change statistics (prev price, delta, months since prev).
4.  Rebuild a monthly price panel per plan (price holds until next change).
5.  Join US CPI and compute real prices + a chained market price index.
6.  Summarise plans (launch -> latest) and the ad-free price gap per service.
7.  Cross-check the whole pipeline against an independent Kaggle dataset and
    write data/processed/validation_report.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

# The tier vocabulary used across the whole project. Mapped from the source's
# plan_key: "with ads" / "no ads" / "add-on".
TIER_RULES = {
    "adSupported": "with ads",
    "select": "with ads",
    "standard": "no ads",
    "premium": "no ads",
    "basic": "no ads",
    "adFreeAddon": "add-on",
}

# Constant-dollar base for real prices: the latest month in the data.
REAL_BASE = "2026-09"

MONTHS = pd.date_range("2010-06-01", "2026-09-01", freq="MS")


# ----------------------------------------------------------------------------
# 1-3. Load, validate, derive event statistics
# ----------------------------------------------------------------------------
def load_events() -> pd.DataFrame:
    df = pd.read_csv(RAW / "prices.csv")
    df["effective_date"] = pd.to_datetime(df["effective_date"], format="%Y-%m-%d")
    df["discontinued"] = df["discontinued"].map({True: True, False: False, "true": True, "false": False})
    df["addon"] = df["addon"].map({True: True, False: False, "true": True, "false": False})

    # Scope: on-demand services except ESPN (a channel pass, not a streaming service).
    df = df[(df["category"] == "onDemand") & (df["service_name"] != "ESPN")].copy()

    df["tier"] = df["plan_key"].map(TIER_RULES)
    df["plan_id"] = df["service_name"] + " | " + df["plan_label"]

    # --- validation -------------------------------------------------------
    checks = {
        "scoped events": len(df),
        "services": df["service_name"].nunique(),
        "plans": df["plan_id"].nunique(),
        "null values": int(df.isna().sum().sum()),
        "duplicate (plan, date)": int(df.duplicated(["plan_id", "effective_date"]).sum()),
        "non-positive prices": int((df["price_usd"] <= 0).sum()),
        "unmapped tiers": int(df["tier"].isna().sum()),
    }
    assert checks["null values"] == 0, "null values in scoped data"
    assert checks["duplicate (plan, date)"] == 0, "duplicate plan/date rows"
    assert checks["non-positive prices"] == 0, "non-positive prices"
    assert checks["unmapped tiers"] == 0, "plan_key missing from TIER_RULES"
    assert checks["plans"] == 20, "expected 20 plans in scope"

    df = df.sort_values(["plan_id", "effective_date"]).reset_index(drop=True)

    # --- derived change statistics --------------------------------------
    g = df.groupby("plan_id", sort=False)
    df["plan_row"] = g.cumcount()
    df["is_launch"] = df["plan_row"] == 0
    df["launch_price"] = g["price_usd"].transform("first")
    df["launch_date"] = g["effective_date"].transform("first")
    df["prev_price"] = g["price_usd"].shift(1)
    df["prev_date"] = g["effective_date"].shift(1)

    df["change_usd"] = (df["price_usd"] - df["prev_price"]).round(2)
    df["change_pct"] = ((df["price_usd"] / df["prev_price"] - 1) * 100).round(1)
    df["months_since_prev"] = ((df["effective_date"] - df["prev_date"]).dt.days / 30.44).round(1)
    df["since_launch_usd"] = (df["price_usd"] - df["launch_price"]).round(2)
    df["since_launch_pct"] = ((df["price_usd"] / df["launch_price"] - 1) * 100).round(1)

    return df, checks


# ----------------------------------------------------------------------------
# 4. Monthly panel: each plan's price holds from its change month until the next
# ----------------------------------------------------------------------------
def build_monthly_panel(events: pd.DataFrame) -> pd.DataFrame:
    ev = events.copy()
    ev["month"] = ev["effective_date"].dt.to_period("M").dt.to_timestamp()
    wide = ev.pivot_table(index="month", columns="plan_id", values="price_usd", aggfunc="last")
    wide = wide.reindex(MONTHS).ffill()

    panel = (
        wide.reset_index(names="month")
        .melt(id_vars="month", var_name="plan_id", value_name="price")
        .dropna()
    )
    meta = events[["plan_id", "service_name", "plan_label", "plan_key", "tier", "addon", "discontinued"]] \
        .drop_duplicates()
    panel = panel.merge(meta, on="plan_id", how="left")
    panel["month"] = pd.to_datetime(panel["month"])
    return panel.sort_values(["plan_id", "month"]).reset_index(drop=True)


# ----------------------------------------------------------------------------
# 5. CPI join + chained market index
# ----------------------------------------------------------------------------
def enrich_with_cpi(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cpi = pd.read_csv(RAW / "CPIAUCSL.csv")
    cpi.columns = ["month", "cpi"]
    cpi["month"] = pd.to_datetime(cpi["month"]).dt.to_period("M").dt.to_timestamp()
    cpi = cpi[cpi["month"].isin(MONTHS)].reset_index(drop=True)
    assert cpi["month"].min() == MONTHS[0] and cpi["month"].max() == MONTHS[-1], "CPI coverage gap"

    # The BLS series has one genuinely missing month (Oct 2025 — collection gap).
    # Interpolate it linearly between its neighbours and flag the row so the
    # imputation is visible in the processed data rather than hidden.
    cpi["cpi_imputed"] = cpi["cpi"].isna()
    cpi["cpi"] = cpi["cpi"].interpolate(method="linear")
    assert cpi["cpi"].isna().sum() == 0, "unfilled CPI gaps"

    base_cpi = float(cpi.loc[cpi["month"] == pd.Timestamp(REAL_BASE), "cpi"].iloc[0])
    cpi["cpi_index_2010"] = (cpi["cpi"] / float(cpi.loc[0, "cpi"]) * 100).round(2)
    cpi["cpi_real_base"] = (base_cpi / cpi["cpi"]).round(4)

    p = panel.merge(cpi, on="month", how="left")
    assert p["cpi"].isna().sum() == 0
    p["price_real"] = (p["price"] * p["cpi_real_base"]).round(2)  # constant REAL_BASE dollars

    # Chained, equal-weight market price index (matched-model, BLS-style):
    # each month only compares plans present in both months, so launches and
    # retirements never move the index by themselves.
    wide = p.pivot_table(index="month", columns="plan_id", values="price", aggfunc="last").reindex(MONTHS)
    ratio = wide / wide.shift(1)
    chain = np.exp(np.log(ratio).mean(axis=1, skipna=True))
    market = pd.DataFrame({"month": MONTHS})
    # .to_numpy() because chain carries a DatetimeIndex that would not align
    # against market's RangeIndex and would silently produce NaNs
    market["market_index"] = (chain.cumprod().fillna(1.0) * 100).round(2).to_numpy()
    market = market.merge(cpi[["month", "cpi_index_2010"]], on="month")
    market = market.rename(columns={"cpi_index_2010": "cpi_index"})
    return p, market


# ----------------------------------------------------------------------------
# 6. Plan summary + ad-free gap
# ----------------------------------------------------------------------------
def build_plan_summary(events: pd.DataFrame) -> pd.DataFrame:
    last = events.groupby("plan_id", sort=False).tail(1).set_index("plan_id")
    n_changes = events[~events["is_launch"]].groupby("plan_id").size()
    n_down = events[events["change_usd"] < 0].groupby("plan_id").size()
    months = ((last["effective_date"] - last["launch_date"]).dt.days / 30.44).clip(lower=1)

    s = pd.DataFrame({
        "plan_id": last.index,
        "service_name": last["service_name"],
        "plan_label": last["plan_label"],
        "tier": last["tier"],
        "addon": last["addon"],
        "discontinued": last["discontinued"],
        "launch_date": last["launch_date"],
        "launch_price": last["launch_price"],
        "latest_date": last["effective_date"],
        "latest_price": last["price_usd"],
        "since_launch_usd": last["since_launch_usd"],
        "since_launch_pct": last["since_launch_pct"],
        "n_changes": n_changes.reindex(last.index).fillna(0).astype(int),
        "n_decreases": n_down.reindex(last.index).fillna(0).astype(int),
    })
    s["cagr_pct"] = ((s["latest_price"] / s["launch_price"]) ** (12 / months.reindex(last.index)) - 1) * 100
    s["months_tracked"] = months.reindex(last.index).round(1)
    return s.sort_values("since_launch_pct", ascending=False).reset_index(drop=True)


def build_ad_gap(panel: pd.DataFrame) -> pd.DataFrame:
    use = panel[(~panel["addon"]) & (~panel["discontinued"])]
    cheap = use.groupby(["month", "service_name", "tier"])["price"].min().unstack("tier")
    gap = cheap.dropna(subset=["with ads", "no ads"]).copy()
    gap["gap_usd"] = (gap["no ads"] - gap["with ads"]).round(2)
    gap["gap_pct"] = ((gap["no ads"] / gap["with ads"] - 1) * 100).round(1)
    return gap.reset_index()[["month", "service_name", "with ads", "no ads", "gap_usd", "gap_pct"]]


# ----------------------------------------------------------------------------
# 7. Cross-check against the independent Kaggle dataset
# ----------------------------------------------------------------------------
KAGGLE_MAP = {  # Kaggle service name -> tracker service_name
    "Netflix": "Netflix", "Disney+": "Disney+", "Hulu": "Hulu", "HBO Max": "HBO Max",
    "Apple TV+": "Apple TV", "Peacock": "Peacock", "Paramount+": "Paramount+",
    "Prime Video": "Prime Video",
}


def crosscheck_kaggle(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kag = pd.read_csv(RAW / "streaming_service.csv")
    kag["month"] = pd.to_datetime(kag["date"], format="%b-%Y").dt.to_period("M").dt.to_timestamp()
    kag["service_name"] = kag["service"].map(KAGGLE_MAP)
    kag = kag.dropna(subset=["service_name"])
    kag = kag.rename(columns={"price": "kaggle_price"})[["service_name", "month", "kaggle_price"]]

    # Kaggle claims "lowest-cost, no-ads" per month, so allow discontinued
    # plans (they were the cheapest ad-free option while they existed).
    cheapest = (panel[panel["tier"] == "no ads"]
                .groupby(["month", "service_name"])["price"].min()
                .rename("tracker_price").reset_index())

    m = kag.merge(cheapest, on=["month", "service_name"], how="left").dropna(subset=["tracker_price"])
    m["match"] = np.isclose(m["kaggle_price"], m["tracker_price"], atol=0.01)
    mismatches = m[~m["match"]].sort_values(["service_name", "month"]).reset_index(drop=True)

    per_service = (m.groupby("service_name")
                   .agg(months_compared=("match", "size"), months_matching=("match", "sum"))
                   .reset_index())
    per_service["agreement_pct"] = (per_service["months_matching"] / per_service["months_compared"] * 100).round(1)
    return m, mismatches, per_service


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def write_report(checks, panel, summary, gap, market, kc_matches, kc_mismatch, kc_per_svc) -> None:
    ev = pd.read_csv(OUT / "prices_clean.csv", parse_dates=["effective_date"])
    hikes = ev[(~ev["is_launch"]) & (ev["change_usd"] > 0)]
    cuts = ev[(~ev["is_launch"]) & (ev["change_usd"] < 0)]

    lines = [
        "# Data preparation — validation report",
        "",
        f"Generated by `src/data_prep.py` from `data/raw/`. Latest month covered: **{panel['month'].max():%b %Y}**.",
        "",
        "## 1. Input validation (Streaming Price Tracker, scoped to onDemand minus ESPN)",
        "",
        "| check | result |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in checks.items()]
    lines += [
        "",
        f"- Price-change events (non-launch): **{len(hikes) + len(cuts)}** — "
        f"{len(hikes)} increases, {len(cuts)} decreases.",
        f"- Monthly panel: **{len(panel):,}** rows "
        f"({panel['plan_id'].nunique()} plans × months they exist).",
        f"- Plans summarised: **{len(summary)}**; services with an ad-free gap: "
        f"**{gap['service_name'].nunique()}**.",
        "",
        "## 2. Derived variables",
        "",
        "| variable | table | definition |",
        "|---|---|---|",
        "| `change_usd`, `change_pct` | prices_clean | new price vs previous price of the same plan |",
        "| `months_since_prev` | prices_clean | days between changes / 30.44 |",
        "| `since_launch_usd/_pct`, `cagr_pct` | prices_clean, plan_summary | growth from the plan's first recorded price |",
        "| `price_real` | monthly_prices | price deflated by CPIAUCSL into constant " + REAL_BASE + " dollars |",
        "| `market_index` | market_index | chained equal-weight index of all plans (matched-model, BLS-style); a plan launching or retiring never moves it by itself |",
        "| `gap_usd`, `gap_pct` | ad_gap | cheapest no-ads minus cheapest with-ads plan per service/month (add-ons and discontinued plans excluded) |",
        "",
        "## 3. Cross-check vs the independent Kaggle dataset",
        "",
        "Kaggle's `streaming_service.csv` states it tracks the *lowest-cost, no-ads* plan per service per month.",
        "We therefore compare it against the cheapest no-ads plan in our main dataset (discontinued plans "
        "allowed — they were the cheapest option while they existed).",
        "",
        "| service | months compared | months matching | agreement % |",
        "|---|---|---|---|",
    ]
    for _, r in kc_per_svc.iterrows():
        lines.append(f"| {r['service_name']} | {int(r['months_compared'])} | "
                     f"{int(r['months_matching'])} | {r['agreement_pct']} |")
    agree = kc_matches["match"].mean() * 100
    lines += [
        "",
        f"**Overall agreement: {agree:.1f}% of {len(kc_matches)} overlapping service-months.**",
        "",
        f"Disagreements found: **{len(kc_mismatch)}** service-months, in exactly two patterns "
        "(full table: `kaggle_mismatches.csv`):",
        "",
        "1. **Recording lag (10 service-months — Hulu, Apple TV, HBO Max, Peacock at single change points).** "
        "The two datasets disagree only by *when* a change is dated: the tracker records exact effective dates "
        "(e.g. Hulu $14.99 from 2022-10-10) while Kaggle records the change one to three months later "
        "(Dec 2022). Same prices, different timestamps — the tracker's daily precision wins for event analysis, "
        "which is why Q2 uses its `effective_date`.",
        "2. **Tier switch in Netflix (4 service-months, Oct 2023 – Jan 2024).** Kaggle jumps from $9.99 to "
        "**$15.49**, which is Netflix **Standard**'s price; the actual cheapest ad-free plan (Basic) went to "
        "**$11.99**. Kaggle spliced two tiers, producing a fictitious +55% increase. Our main dataset models "
        "tiers explicitly, so this cannot happen silently. Any +55% Netflix figure taken from the Kaggle file "
        "alone is a tier switch, not a price hike.",
        "",
        "Only the Netflix pattern affects conclusions (it inflates a headline increase); the rest would only "
        "shift single months in a timeline.",
        "",
        "## 4. Known caveats",
        "",
        "- Prices are US standard monthly list prices; promotions, annual plans and bundles are excluded "
        "(scope of the source).",
        "- `launch_date`/`launch_price` are the *first recorded* price change, which may post-date the plan's "
        "actual launch (e.g. Netflix's earliest recorded row is Nov 2010).",
        "- Netflix Basic is flagged `discontinued`; the source notes it was phased out for new subscribers "
        "2023-07 and ended for all subscribers 2024-07.",
        "- CPI is national all-items inflation (BLS via FRED). It deflates prices; it does not claim anything "
        "about this industry's costs.",
        "- **Missing values:** the CPI series has no published Oct 2025 value (BLS collection gap). It is filled "
        "by linear interpolation between Sep and Nov 2025 and flagged in `monthly_prices.csv` "
        "(`cpi_imputed`); the price data itself has no missing values.",
    ]
    (OUT / "validation_report.md").write_text("\n".join(lines) + "\n")


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main() -> None:
    events, checks = load_events()
    panel = build_monthly_panel(events)
    panel, market = enrich_with_cpi(panel)
    summary = build_plan_summary(events)
    gap = build_ad_gap(panel)
    kc_matches, kc_mismatch, kc_per_svc = crosscheck_kaggle(panel)

    events.to_csv(OUT / "prices_clean.csv", index=False)
    panel.to_csv(OUT / "monthly_prices.csv", index=False)
    summary.to_csv(OUT / "plan_summary.csv", index=False)
    gap.to_csv(OUT / "ad_gap.csv", index=False)
    market.to_csv(OUT / "market_index.csv", index=False)
    kc_mismatch.to_csv(OUT / "kaggle_mismatches.csv", index=False)

    # Service brand colours from the source's JSON (CC BY 4.0, credited in README).
    src = json.loads((RAW / "prices.json").read_text())
    colors = {v["name"]: v.get("color") for v in src["services"].values()}
    pd.Series(colors, name="color").rename_axis("service_name").reset_index().to_csv(
        OUT / "service_colors.csv", index=False)

    write_report(checks, panel, summary, gap, market, kc_matches, kc_mismatch, kc_per_svc)

    print("data prep complete ->", OUT)
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name:28s} {f.stat().st_size:>8,} bytes")


if __name__ == "__main__":
    main()
