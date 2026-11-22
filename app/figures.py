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
from plotly.subplots import make_subplots

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"

# Tier palette — identical in every chart so colour always means the same thing.
TIER_COLORS = {"no ads": "#2A6F97", "with ads": "#E9A23B", "add-on": "#8D99AE"}
# Fallback service palette (overridden by the source's own brand colours below).
SERVICE_FALLBACK = px.colors.qualitative.Set2

BASE_LAYOUT = dict(template="plotly_white", margin=dict(l=40, r=20, t=30, b=44), height=400)

# One height for every chart that sits in a paired grid row, so no card is
# stretched to match a taller neighbour (which used to leave dead space).
CHART_H = 400

# Theme-dependent palettes. Colours that carry meaning (tier palette, service
# brand colours) stay identical in both themes, so the encoding never changes;
# only paper, text and gridline colours are swapped.
THEME = {
    "light": dict(
        template="plotly_white",
        paper="#ffffff", plot="#ffffff",
        text="#212529", text_dim="#495057", muted="#6c757d",
        grid="#e9ecef", axis="#ced4da", legend_bg="rgba(255,255,255,0.9)",
    ),
    "dark": dict(
        template="plotly_dark",
        paper="#1a1f27", plot="#1a1f27",
        text="#e6edf3", text_dim="#b7c3d0", muted="#8b98a8",
        grid="#2b3442", axis="#3b4657", legend_bg="rgba(26,31,39,0.9)",
    ),
}


def apply_theme(fig: go.Figure, dark: bool = False) -> go.Figure:
    """Recolour a finished figure for the active theme.

    Applied as a post-process in the callbacks, so each figure builder stays
    theme-agnostic and its signature does not change.
    """
    t = THEME["dark" if dark else "light"]

    fig.update_layout(
        template=t["template"],
        paper_bgcolor=t["paper"],
        plot_bgcolor=t["plot"],
        font=dict(color=t["text"]),
        title=dict(font=dict(color=t["text"])),
        legend=dict(bgcolor=t["legend_bg"], font=dict(color=t["text_dim"])),
        hoverlabel=dict(bgcolor=t["paper"], bordercolor=t["axis"],
                        font=dict(color=t["text"])),
    )
    fig.update_xaxes(gridcolor=t["grid"], zerolinecolor=t["axis"],
                     linecolor=t["axis"], tickfont=dict(color=t["text_dim"]),
                     title_font=dict(color=t["text_dim"]))
    fig.update_yaxes(gridcolor=t["grid"], zerolinecolor=t["axis"],
                     linecolor=t["axis"], tickfont=dict(color=t["text_dim"]),
                     title_font=dict(color=t["text_dim"]))

    # data labels written by imshow/text traces, and subplot titles
    for tr in fig.data:
        if getattr(tr, "textfont", None) is not None:
            tr.textfont = dict(color=t["text"])
    if fig.layout.annotations:
        fig.update_annotations(font_color=t["text"])
    return fig


def load_data() -> dict[str, pd.DataFrame]:
    """Load all processed tables once at app start."""
    d = {
        "events": pd.read_csv(PROC / "prices_clean.csv", parse_dates=["effective_date", "launch_date", "prev_date"]),
        "monthly": pd.read_csv(PROC / "monthly_prices.csv", parse_dates=["month"]),
        "summary": pd.read_csv(PROC / "plan_summary.csv", parse_dates=["launch_date", "latest_date"]),
        "gap": pd.read_csv(PROC / "ad_gap.csv", parse_dates=["month"]),
        "market": pd.read_csv(PROC / "market_index.csv", parse_dates=["month"]),
        "yoy": pd.read_csv(PROC / "yoy_comparison.csv"),
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
                   height=min(560, max(CHART_H, 26 * len(df) + 80)), showlegend=True)


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
                            "Change: %{customdata[3]:+.2f} USD (%{customdata[4]:+.1f}%)"
                            "<extra></extra>")
    return _layout(fig, height=CHART_H, showlegend=True)


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
    return _layout(fig, height=CHART_H)


# ---------------------------------------------------------------------------
# Q3a — cost of going ad-free over time
# ---------------------------------------------------------------------------
def fig_gap_lines(gap: pd.DataFrame, service_colors: dict[str, str],
                  cols: int = 4) -> go.Figure:
    """Small multiples: one panel per service, so seven series never overlap.

    A single frame with seven stepped lines drew the same gap values (5, 6, 7
    dollars) on top of each other, and the panels start in different years, so
    the lines were impossible to trace or compare. One row per service fixes
    both: each panel answers "how did this service's ad premium move", and the
    shared x and y scales keep the panels comparable.
    """
    if gap.empty:
        return empty_fig()

    df = gap.copy()
    services = sorted(df["service_name"].unique())
    n = len(services)
    cols = max(1, min(cols, n))
    rows = (n + cols - 1) // cols

    # On a single row, shared_xaxes would hide every year label, so each panel
    # keeps its own x axis; with several rows only the bottom row needs them.
    fig = make_subplots(
        rows=rows, cols=cols, shared_xaxes=(rows > 1), shared_yaxes=True,
        subplot_titles=services, vertical_spacing=0.22, horizontal_spacing=0.06,
    )

    for i, svc in enumerate(services):
        r, c = i // cols + 1, i % cols + 1
        sub = df[df["service_name"] == svc].sort_values("month")
        color = service_colors.get(svc, "#2A6F97")
        fig.add_trace(go.Scatter(
            x=sub["month"], y=sub["gap_usd"], mode="lines",
            name=svc, showlegend=False,
            line=dict(color=color, width=2.5, shape="hv"),
            fill="tozeroy", fillcolor=_rgba(color, 0.13),
            customdata=np.stack([sub["with ads"], sub["no ads"], sub["gap_pct"]], axis=-1),
            hovertemplate=("<b>" + svc + "</b><br>%{x|%b %Y}<br>"
                           "Ad-free costs +$%{y:.2f} more<br>"
                           "with ads $%{customdata[0]:.2f} → no ads $%{customdata[1]:.2f} "
                           "(+%{customdata[2]:.0f}%)<extra></extra>"),
        ), row=r, col=c)

        # start and end labels, so each panel reads on its own
        first, last = sub.iloc[0], sub.iloc[-1]
        fig.add_annotation(x=last["month"], y=last["gap_usd"],
                           text=f"<b>${last['gap_usd']:.2f}</b>", showarrow=False,
                           xanchor="right", yanchor="bottom",
                           font=dict(size=10, color=color), row=r, col=c)

    # With shared_yaxes the title lands on the bottom-left panel only, which reads
    # as if it labels one chart. Put it on the global y axis instead.
    fig.update_yaxes(title_text="Extra USD/month for no-ads",
                     title_font=dict(size=11), row=rows, col=1)
    fig.update_layout(yaxis=dict(title_text="Extra USD/month for no-ads",
                                 title_font=dict(size=11)))
    # make_subplots forces showticklabels=False on the linked axes; re-enable
    # them explicitly or the panels have no dates at all.
    if rows == 1:
        fig.update_xaxes(showticklabels=True, tickformat="%Y", nticks=4,
                         tickfont=dict(size=9))
    else:
        fig.update_xaxes(showticklabels=False)
        fig.update_xaxes(showticklabels=True, tickformat="%Y", nticks=4,
                         tickfont=dict(size=9), row=rows)
    fig.update_yaxes(tickfont=dict(size=9))
    fig.update_annotations(font_size=11)
    return _layout(fig, height=CHART_H + (60 if rows > 1 else 0), showlegend=False,
                   margin=dict(l=56, r=20, t=40, b=40))


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


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
    return _layout(fig, xaxis_title="Monthly price (USD)", height=CHART_H,
                   showlegend=True)


# ---------------------------------------------------------------------------
# Q4a — price index vs inflation, rebased at the window start
# ---------------------------------------------------------------------------
def fig_yoy_inflation(yoy: pd.DataFrame) -> go.Figure:
    """Paired bars: each year's streaming price change vs that year's inflation.

    Deliberately not cumulative. Every year stands alone, so a single early
    price event cannot distort the whole series the way it does inside a
    compounding index.
    """
    if yoy.empty:
        return empty_fig()

    df = yoy.copy()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["year"], y=df["streaming_yoy"], name="Streaming prices",
        marker_color="#C1121F",
        customdata=np.stack([df["gap_pts"], df["coverage"], df["ratio"]], axis=-1),
        hovertemplate=("<b>%{x}</b><br>"
                       "Streaming prices rose %{y:.1f}%<br>"
                       "Gap versus inflation: %{customdata[0]:+.1f} points "
                       "(%{customdata[2]:.2f}x)<extra></extra>"),
    ))
    fig.add_trace(go.Bar(
        x=df["year"], y=df["cpi_yoy"], name="US inflation (CPI-U)",
        marker_color="#ADB5BD",
        customdata=np.stack([df["gap_pts"], df["coverage"], df["ratio"]], axis=-1),
        hovertemplate=("<b>%{x}</b><br>"
                       "US inflation %{y:.1f}%<br>"
                       "Gap versus streaming: %{customdata[0]:+.1f} points<extra></extra>"),
    ))

    # Label only the years that carry the story: the recent surge.
    for r in df[df["year"] >= 2022].itertuples():
        fig.add_annotation(x=r.year, y=max(r.streaming_yoy, r.cpi_yoy) + 0.6,
                           text=f"<b>{r.ratio:.1f}x</b>", showarrow=False,
                           font=dict(size=10, color="#C1121F" if r.outpaced else "#495057"))
    fig.add_hline(y=0, line=dict(color="#495057", width=1))

    return _layout(fig, barmode="group", bargap=0.25, bargroupgap=0.08,
                   yaxis_title="Price change that year (%)",
                   height=CHART_H, showlegend=True)


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
                   yaxis_title="Price growth since launch (%)", height=CHART_H, showlegend=True)


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
                     custom_data=["plan_id", "effective_date", "price_usd", "prev_price",
                                  "change_usd", "change_pct"])
    for tr in fig.data:
        tr.marker.line = dict(width=1, color="white")
        tr.hovertemplate = ("<b>%{customdata[0]}</b><br>"
                            "%{customdata[1]|%d %b %Y}: $%{customdata[3]:.2f} → $%{customdata[2]:.2f}<br>"
                            "Hike: %{customdata[4]:+.2f} USD (%{customdata[5]:+.1f}%) "
                            "after %{x:.1f} months<extra></extra>")
    fig.add_hline(y=0, line=dict(color="#ADB5BD", width=1))
    return _layout(fig, xaxis_title="Months since previous change",
                   yaxis_title="Size of change (%)", height=CHART_H, showlegend=True)


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
    return _layout(fig, yaxis_title="USD per month", height=CHART_H)
