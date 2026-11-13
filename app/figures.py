"""Figure builders for the Streamflation dashboard.

Each function is pure: it takes prepared data (already filtered) and returns a
Plotly figure. No I/O here — app/app.py owns filtering and callbacks.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

# Tier palette — identical in every chart so colour always means the same thing.
TIER_COLORS = {"no ads": "#2A6F97", "with ads": "#E9A23B", "add-on": "#8D99AE"}
# Fallback service palette (overridden by the source's own brand colours below).
SERVICE_FALLBACK = px.colors.qualitative.Set2

BASE_LAYOUT = dict(template="plotly_white", margin=dict(l=40, r=20, t=30, b=44), height=420)


def load_data() -> dict[str, pd.DataFrame]:
    """Load all processed tables once at app start."""
    d = {
        "events": pd.read_csv(PROC / "prices_clean.csv", parse_dates=["effective_date", "launch_date", "prev_date"]),
        "monthly": pd.read_csv(PROC / "monthly_prices.csv", parse_dates=["month"]),
        "summary": pd.read_csv(PROC / "plan_summary.csv", parse_dates=["launch_date", "latest_date"]),
        "gap": pd.read_csv(PROC / "ad_gap.csv", parse_dates=["month"]),
        "market": pd.read_csv(PROC / "market_index.csv", parse_dates=["month"]),
    }
    colors = pd.read_csv(PROC / "service_colors.csv")
    palette = {r.service_name: r.color for r in colors.itertuples()}
    fallback = dict(zip(sorted(d["events"]["service_name"].unique()), SERVICE_FALLBACK))
    d["service_colors"] = {s: palette.get(s, fallback.get(s)) for s in fallback}
    return d


def empty_fig(message: str = "No data for this selection") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper",
                       showarrow=False, font=dict(size=14, color="#888"))
    fig.update_xaxes(visible=False), fig.update_yaxes(visible=False)
    return fig.update_layout(**BASE_LAYOUT)


def _layout(fig: go.Figure, **kw) -> go.Figure:
    fig.update_layout(**{**BASE_LAYOUT, **kw})
    # horizontal legend on top, no auto legend title (px sets one from the column name)
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=""))
    return fig


# ---------------------------------------------------------------------------
# Q1 — dumbbell: launch price -> latest price per plan
# ---------------------------------------------------------------------------
def fig_dumbbell(summary: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return empty_fig()
    df = summary.sort_values("since_launch_pct", ascending=True)  # biggest rise on top
    order = df["plan_id"].tolist()
    fig = go.Figure()
    for r in df.itertuples():
        fig.add_trace(go.Scatter(
            x=[r.launch_price, r.latest_price], y=[r.plan_id, r.plan_id],
            mode="lines", line=dict(color="#C7CDD4", width=3),
            hoverinfo="skip", showlegend=False))
    for when, col in (("At launch", "#9AA5B1"), ("Latest", "#2A6F97")):
        vals = df["launch_price"] if when == "At launch" else df["latest_price"]
        dates = df["launch_date"] if when == "At launch" else df["latest_date"]
        fig.add_trace(go.Scatter(
            x=vals, y=df["plan_id"], mode="markers", name=when,
            marker=dict(size=11, color=col,
                        line=dict(width=1, color="white")),
            customdata=np.stack([dates.dt.strftime("%b %Y"),
                                 df["tier"], df["since_launch_usd"],
                                 df["since_launch_pct"]], axis=-1),
            hovertemplate=("<b>%{y}</b><br>" + when + ": $%{x:.2f} (%{customdata[0]})<br>"
                           "Change: +$%{customdata[2]:.2f} (+%{customdata[3]:.1f}%)<br>"
                           "Tier: %{customdata[1]}<extra></extra>")))
    return _layout(fig, xaxis_title="Monthly price (USD)", yaxis_title=None,
                   yaxis=dict(categoryorder="array", categoryarray=order),
                   height=max(360, 30 * len(df) + 90), showlegend=True)


# ---------------------------------------------------------------------------
# Q2a — event timeline: hikes cluster in time?
# ---------------------------------------------------------------------------
def fig_timeline(events: pd.DataFrame, service_colors: dict[str, str]) -> go.Figure:
    df = events[~events["is_launch"]].copy()  # one dot per price *change*
    if df.empty:
        return empty_fig()
    df["size"] = df["change_pct"].abs().clip(lower=1.5)
    fig = px.scatter(
        df, x="effective_date", y="service_name", size="size", color="service_name",
        color_discrete_map=service_colors, size_max=26,
        labels={"service_name": "", "effective_date": ""},
        custom_data=["plan_label", "price_usd", "prev_price", "change_usd", "change_pct"],
    )
    for tr in fig.data:
        tr.marker.line = dict(width=1, color="white")
        tr.hovertemplate = ("<b>%{y}</b> — %{customdata[0]}<br>"
                            "%{x|%d %b %Y}: $%{customdata[2]:.2f} → $%{customdata[1]:.2f}<br>"
                            "Change: %{customdata[3]:+.2f} USD ({:+.1f}%)<extra></extra>")
    return _layout(fig, height=380, showlegend=True)


# ---------------------------------------------------------------------------
# Q2b — service x year heatmap
# ---------------------------------------------------------------------------
def fig_heatmap(events: pd.DataFrame) -> go.Figure:
    if events.empty:
        return empty_fig()
    hikes = events[events["change_usd"] > 0].copy()
    hikes["year"] = hikes["effective_date"].dt.year
    matrix = pd.crosstab(hikes["service_name"], hikes["year"])
    matrix = matrix.reindex(columns=range(2010, 2027), fill_value=0)
    matrix.index.name = None  # avoid a stray "service_name" axis label
    fig = px.imshow(matrix, text_auto=True, color_continuous_scale="Reds", aspect="auto",
                    labels=dict(x="Year", y="", color=""))
    fig.update_traces(hovertemplate="%{y}<br>%{x}: %{z} price increase(s)<extra></extra>")
    fig.update_layout(coloraxis_colorbar=dict(thickness=12))
    return _layout(fig, height=380)


# ---------------------------------------------------------------------------
# Q3a — cost of going ad-free over time
# ---------------------------------------------------------------------------
def fig_gap_lines(gap: pd.DataFrame, service_colors: dict[str, str]) -> go.Figure:
    if gap.empty:
        return empty_fig()
    fig = px.line(gap, x="month", y="gap_usd", color="service_name", line_shape="hv",
                  color_discrete_map=service_colors,
                  labels={"month": "", "gap_usd": "Extra USD per month for no-ads",
                          "service_name": ""},
                  custom_data=["with ads", "no ads", "gap_pct"])
    for tr in fig.data:
        tr.hovertemplate = ("<b>%{fullData.name}</b><br>%{x|%b %Y}: +%{y:.2f} USD to go ad-free<br>"
                            "with ads $%{customdata[0]:.2f} → no ads $%{customdata[1]:.2f} "
                            "(+%{customdata[2]:.1f}%)<extra></extra>")
    return _layout(fig, height=420, showlegend=True)


# ---------------------------------------------------------------------------
# Q3b — current ad gap per service (dumbbell)
# ---------------------------------------------------------------------------
def fig_gap_dumbbell(gap: pd.DataFrame) -> go.Figure:
    if gap.empty:
        return empty_fig()
    latest = gap.groupby("service_name").tail(1).sort_values("gap_usd", ascending=True)
    names = latest["service_name"].tolist()
    ads = latest["with ads"].tolist()
    noads = latest["no ads"].tolist()
    gaps = latest["gap_usd"].tolist()
    gaps_pct = latest["gap_pct"].tolist()
    fig = go.Figure()
    for name, a, n in zip(names, ads, noads):
        fig.add_trace(go.Scatter(
            x=[a, n], y=[name, name],
            mode="lines", line=dict(color="#C7CDD4", width=3), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=ads, y=names, mode="markers",
                             name="With ads", marker=dict(size=11, color=TIER_COLORS["with ads"]),
                             customdata=np.stack([gaps, gaps_pct], axis=-1),
                             hovertemplate="<b>%{y}</b> — with ads $%{x:.2f}<br>"
                                           "Ad-free premium: +$%{customdata[0]:.2f} "
                                           "(+%{customdata[1]:.1f}%)<extra></extra>"))
    fig.add_trace(go.Scatter(x=noads, y=names, mode="markers",
                             name="No ads", marker=dict(size=11, color=TIER_COLORS["no ads"]),
                             customdata=np.stack([gaps, gaps_pct], axis=-1),
                             hovertemplate="<b>%{y}</b> — no ads $%{x:.2f}<br>"
                                           "Ad-free premium: +$%{customdata[0]:.2f} "
                                           "(+%{customdata[1]:.1f}%)<extra></extra>"))
    return _layout(fig, xaxis_title="Monthly price (USD)", height=380,
                   showlegend=True)


# ---------------------------------------------------------------------------
# Q4a — price index vs inflation, rebased at the window start
# ---------------------------------------------------------------------------
def fig_index(monthly: pd.DataFrame, market: pd.DataFrame, start: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    for col, name, style in (("market_index", "Tracked streaming prices (chained index)",
                              dict(color="#C1121F", width=3)),
                             ("cpi_index", "US inflation (CPI-U)",
                              dict(color="#6C757D", width=2.5, dash="dash"))):
        s = market[market["month"] >= start]
        if s.empty:
            return empty_fig("Window starts after the data ends")
        base = float(s[col].iloc[0])
        fig.add_trace(go.Scatter(x=s["month"], y=s[col] / base * 100, mode="lines",
                                 name=name, line=style,
                                 hovertemplate="%{x|%b %Y}: %{y:.1f}<extra>" + name + "</extra>"))
    fig.add_hline(y=100, line=dict(color="#ADB5BD", width=1))
    return _layout(fig, yaxis_title="Index (window start = 100)",
                   height=420, showlegend=True)


# ---------------------------------------------------------------------------
# Q4b — per-plan growth vs inflation over the plan's own lifetime
# ---------------------------------------------------------------------------
def fig_growth_vs_inflation(summary: pd.DataFrame, monthly: pd.DataFrame) -> go.Figure:
    if summary.empty:
        return empty_fig()
    cpi = (monthly.sort_values("month").groupby("plan_id").agg(cpi0=("cpi", "first"), cpi1=("cpi", "last")))
    df = summary.merge(cpi, on="plan_id", how="inner")
    df["inflation_pct"] = ((df["cpi1"] / df["cpi0"] - 1) * 100).round(1)
    fig = px.scatter(df, x="inflation_pct", y="since_launch_pct", color="tier",
                     color_discrete_map=TIER_COLORS, size="months_tracked", size_max=22,
                     custom_data=["plan_id", "launch_price", "latest_price",
                                  df["launch_date"].dt.strftime("%b %Y"),
                                  df["latest_date"].dt.strftime("%b %Y"),
                                  "since_launch_usd", "months_tracked"])
    lim = float(max(df["inflation_pct"].max(), df["since_launch_pct"].max())) + 15
    fig.add_trace(go.Scatter(x=[0, lim], y=[0, lim], mode="lines", showlegend=False,
                             line=dict(color="#ADB5BD", width=1.5, dash="dot"),
                             hoverinfo="skip"))
    fig.add_annotation(x=lim * 0.72, y=lim * 0.86, text="above this line =<br>outpaced inflation",
                       showarrow=False, font=dict(size=11, color="#888"))
    for tr in fig.data[:-1]:
        tr.marker.line = dict(width=1, color="white")
        tr.hovertemplate = ("<b>%{customdata[0]}</b> <i>(%{customdata[6]:.0f} months)</i><br>"
                            "Inflation since launch: +%{x:.1f}%<br>"
                            "Price growth: +%{y:.1f}% (+$%{customdata[5]:.2f})<br>"
                            "$%{customdata[1]:.2f} (%{customdata[3]}) → "
                            "$%{customdata[2]:.2f} (%{customdata[4]})<extra></extra>")
    return _layout(fig, xaxis_title="Inflation since launch (%)",
                   yaxis_title="Price growth since launch (%)", height=420, showlegend=True)


# ---------------------------------------------------------------------------
# Q5 — small steps or big jumps?
# ---------------------------------------------------------------------------
def fig_hike_scatter(events: pd.DataFrame) -> go.Figure:
    df = events[(~events["is_launch"]) & events["months_since_prev"].notna()].copy()
    if df.empty:
        return empty_fig()
    df["change_abs"] = df["change_usd"].abs()  # bubble scale; sign shows in the y position
    fig = px.scatter(df, x="months_since_prev", y="change_pct", color="tier",
                     color_discrete_map=TIER_COLORS,
                     size="change_abs", size_max=26,
                     custom_data=["plan_id", "effective_date", "price_usd", "prev_price", "change_usd"])
    for tr in fig.data:
        tr.marker.line = dict(width=1, color="white")
        tr.hovertemplate = ("<b>%{customdata[0]}</b><br>"
                            "%{customdata[1]|%d %b %Y}: $%{customdata[3]:.2f} → $%{customdata[2]:.2f}<br>"
                            "Hike: +$%{customdata[4]:.2f} ({:+.1f}%) after %{x:.1f} months<extra></extra>")
    fig.add_hline(y=0, line=dict(color="#ADB5BD", width=1))
    return _layout(fig, xaxis_title="Months since previous change",
                   yaxis_title="Size of change (%)", height=420, showlegend=True)


# ---------------------------------------------------------------------------
# Calculator — total monthly cost of a chosen bundle
# ---------------------------------------------------------------------------
def fig_calculator(monthly: pd.DataFrame, services: list[str], tier_mode: str,
                   service_colors: dict[str, str]) -> go.Figure:
    mode_map = {"Cheapest ad-free": "no ads", "Cheapest with ads": "with ads"}
    pool = monthly[(~monthly["addon"]) & (~monthly["discontinued"])]
    pool = pool[pool["service_name"].isin(services)]
    if tier_mode in mode_map:
        pool = pool[pool["tier"] == mode_map[tier_mode]]
    if pool.empty:
        return empty_fig("No plans match — pick at least one service")

    # cheapest matching plan per service per month (plan prices change over time)
    pick = (pool.groupby(["month", "service_name"])["price"].min()
            .rename("price").reset_index())
    total = pick.groupby("month")["price"].sum().reset_index(name="total")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=total["month"], y=total["total"], mode="lines", fill="tozeroy",
                             line=dict(color="#2A6F97", width=2, shape="hv"),
                             fillcolor="rgba(42,111,151,0.15)", name="Total monthly cost",
                             hovertemplate="%{x|%b %Y}: <b>$%{y:.2f}</b> / month<extra></extra>"))
    # breakdown by service at the latest month of the window
    latest = pick[pick["month"] == pick["month"].max()]
    fig.add_trace(go.Bar(x=latest["service_name"], y=latest["price"],
                         marker_color=[service_colors.get(s, "#888") for s in latest["service_name"]],
                         name="Latest month breakdown", yaxis="y2", opacity=0.85,
                         hovertemplate="%{x}: $%{y:.2f} / month<extra></extra>"))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", visible=False, showgrid=False))
    return _layout(fig, yaxis_title="USD per month", height=420)
