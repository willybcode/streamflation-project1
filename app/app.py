"""Streamflation — interactive dashboard (Plotly + Dash).

Run with:  python app/app.py   then open http://127.0.0.1:8050

Layout: one analysis window + tier/service filters drive every view (linked
views), a Q1–Q5 chart grid, and a "my subscriptions" cost calculator.
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, dcc, html, no_update
import pandas as pd

from figures import (TIER_COLORS, fig_calculator, fig_dumbbell, fig_gap_dumbbell,
                     fig_gap_lines, fig_growth_vs_inflation, fig_heatmap, fig_index,
                     fig_hike_scatter, fig_timeline, load_data)

DATA = load_data()
MONTHS = pd.date_range("2010-06-01", "2026-09-01", freq="MS")
ALL_SERVICES = sorted(DATA["events"]["service_name"].unique())
ALL_TIERS = ["no ads", "with ads", "add-on"]

app = dash.Dash(__name__, title="Streamflation — streaming price tracker 2010–2026")
server = app.server

GRAPH_CONFIG = {"displaylogo": False, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def card(title: str, question: str, graph_id: str) -> html.Div:
    return html.Div(className="card", children=[
        html.H3(title),
        html.P(question, className="q"),
        dcc.Graph(id=graph_id, config=GRAPH_CONFIG),
    ])


app.layout = html.Div(className="page", children=[
    # ---------------- header ----------------
    html.Div(className="header", children=[
        html.Div([
            html.H1("Streamflation"),
            html.P("An interactive analysis of US streaming price increases, 2010–2026. "
                   "Prices are standard monthly list prices; inflation is US CPI-U.",
                   className="subtitle"),
        ]),
        html.Div(className="kpis", children=[
            html.Div([html.Div(id="kpi1", className="kpi-v", children="–"),
                      html.Div("price increases in window", className="kpi-l")]),
            html.Div([html.Div(id="kpi2", className="kpi-v", children="–"),
                      html.Div("median hike size", className="kpi-l")]),
            html.Div([html.Div(id="kpi3", className="kpi-v", children="–"),
                      html.Div("streaming price index", className="kpi-l")]),
            html.Div([html.Div(id="kpi4", className="kpi-v", children="–"),
                      html.Div("US inflation, same window", className="kpi-l")]),
        ]),
    ]),

    html.Div(className="layout", children=[
        # ---------------- control rail ----------------
        html.Div(className="rail", children=[
            html.H3("Controls"),
            html.Label("Services (searchable; click any chart point to isolate)"),
            dcc.Dropdown(id="services", options=ALL_SERVICES, value=ALL_SERVICES,
                         multi=True, placeholder="All services"),
            html.Label("Plan tier"),
            dcc.Checklist(id="tiers",
                          options=[{"label": f"  {t}", "value": t} for t in ALL_TIERS],
                          value=ALL_TIERS, inline=True,
                          className="tier-checks"),
            html.Label("Analysis window"),
            dcc.RangeSlider(id="window", min=0, max=len(MONTHS) - 1, step=1,
                            value=[0, len(MONTHS) - 1],
                            marks={i: str(y) for i, y in
                                   enumerate(MONTHS.year) if y % 3 == 0 and (i == 0 or y != MONTHS.year[i - 1])},
                            tooltip={"placement": "bottom", "always_visible": False}),
            html.Div(id="window-label", className="muted"),
            dcc.Checklist(id="advanced",
                          options=[{"label": " Include discontinued & add-on plans",
                                    "value": "y"}],
                          value=["y"]),
            html.Button("Reset filters", id="reset", n_clicks=0, className="btn"),
            html.Hr(),
            html.Div([
                html.Strong("How to read this dashboard"),
                html.Ul([
                    html.Li("Q1–Q5 answer the five analysis questions (marked on each card)."),
                    html.Li("Hover anywhere for details; scroll-zoom on any chart."),
                    html.Li("Click a plan row (Q1) or a dot (Q2) to isolate that service."),
                    html.Li("The window control rebases the inflation chart at its start."),
                ], className="muted"),
            ]),
        ]),

        # ---------------- question grid ----------------
        html.Div(className="grid", children=[
            card("Q1 · Price rise since launch",
                 "How much has each plan's price risen since launch — and who leads? "
                 "Dumbbell = launch price → latest price, ordered by growth. "
                 "Click a row to isolate that service.", "fig-q1"),
            card("Q2 · Do hikes cluster in time?",
                 "One dot per price change (size = size of the hike). If competitors "
                 "move together, dots stack on the same date. Click a dot to isolate "
                 "that service.", "fig-q2a"),
            card("Q2 · Increases per service per year",
                 "The same clustering story as counts: dark cells show years when "
                 "whole groups of services raised prices together.", "fig-q2b"),
            card("Q5 · Small steps or big jumps?",
                 "Hike size vs months since the plan's previous change; bubble size = "
                 "absolute change in USD. Bottom-left = frequent small steps; "
                 "top-right = rare big jumps.", "fig-q5"),
            card("Q3 · The price of going ad-free",
                 "Ad-free minus with-ads price: extra USD/month for the cheapest "
                 "no-ads plan over the cheapest with-ads plan (step lines, since "
                 "prices only change on specific dates).", "fig-q3a"),
            card("Q3 · Today's ad-free premium",
                 "Dumbbell per service at the end of the window: with-ads vs no-ads "
                 "price. Hover for the exact premium.", "fig-q3b"),
            card("Q4 · Faster than inflation?",
                 "Chained market price index vs US CPI-U, both rebased at the start of "
                 "the analysis window. The gap between the lines is real price growth.",
                 "fig-q4a"),
            card("Q4 · Every plan vs inflation",
                 "Each bubble is a plan over its own lifetime (size = months tracked). "
                 "Above the dotted line = the price outpaced general inflation.", "fig-q4b"),
        ]),
    ]),

    # ---------------- calculator ----------------
    html.Div(className="card calc", children=[
        html.H3("My subscriptions — monthly cost calculator"),
        html.P("Tick the services you would subscribe to and see what the bundle costs over time. "
               "The step area is the total monthly cost; bars break the latest month down by service.",
               className="q"),
        html.Div(className="calc-controls", children=[
            dcc.Checklist(id="calc-services",
                          options=[{"label": f" {s}", "value": s} for s in ALL_SERVICES],
                          value=ALL_SERVICES[:4], inline=True, className="tier-checks"),
            dcc.RadioItems(id="calc-mode",
                           options=["Cheapest ad-free", "Cheapest with ads", "Cheapest plan overall"],
                           value="Cheapest ad-free", inline=True, className="tier-checks"),
        ]),
        html.Div(id="calc-kpis", className="kpis", children=[
            html.Div([html.Div(id="ckpi1", className="kpi-v", children="–"),
                      html.Div("monthly cost at window end", className="kpi-l")]),
            html.Div([html.Div(id="ckpi2", className="kpi-v", children="–"),
                      html.Div("change across window", className="kpi-l")]),
            html.Div([html.Div(id="ckpi3", className="kpi-v", children="–"),
                      html.Div("biggest single jump", className="kpi-l")]),
        ]),
        dcc.Graph(id="fig-calc", config=GRAPH_CONFIG),
    ]),

    # ---------------- footer ----------------
    html.Footer(children=[
        html.P("Price data: Streaming Price Tracker (streamingpricetracker.com), CC BY 4.0. "
               "Inflation data: U.S. Bureau of Labor Statistics (CPIAUCSL) via FRED. "
               "Cross-check dataset: “Streaming Service Price History” by Takumi Watanabe (Kaggle, CC0). "
               "Service brand colours from Streaming Price Tracker. "
               "Built with Plotly + Dash (PyViz)."),
    ]),
])


# ---------------------------------------------------------------------------
# Shared filtering
# ---------------------------------------------------------------------------
def filtered(services, tiers, advanced, window):
    keep_adv = "y" in (advanced or [])
    ev = DATA["events"]
    mask = ev["service_name"].isin(services) & ev["tier"].isin(tiers)
    if not keep_adv:
        mask &= (~ev["addon"]) & (~ev["discontinued"])
    events = ev[mask]

    mo = DATA["monthly"]
    mask = mo["service_name"].isin(services) & mo["tier"].isin(tiers)
    if not keep_adv:
        mask &= (~mo["addon"]) & (~mo["discontinued"])
    monthly = mo[mask]

    su = DATA["summary"]
    mask = su["service_name"].isin(services) & su["tier"].isin(tiers)
    if not keep_adv:
        mask &= (~su["addon"]) & (~su["discontinued"])
    summary = su[mask]

    w0, w1 = MONTHS[window[0]], MONTHS[window[1]]
    return (events, monthly, summary, DATA["gap"], w0, w1)


@callback(
    Output("kpi1", "children"), Output("kpi2", "children"),
    Output("kpi3", "children"), Output("kpi4", "children"),
    Output("window-label", "children"),
    Output("fig-q1", "figure"), Output("fig-q2a", "figure"), Output("fig-q2b", "figure"),
    Output("fig-q5", "figure"), Output("fig-q3a", "figure"), Output("fig-q3b", "figure"),
    Output("fig-q4a", "figure"), Output("fig-q4b", "figure"),
    Input("services", "value"), Input("tiers", "value"),
    Input("window", "value"), Input("advanced", "value"),
)
def update_all(services, tiers, window, advanced):
    services = services or []
    tiers = tiers or []
    events, monthly, summary, gap, w0, w1 = filtered(services, tiers, advanced, window)

    ev_w = events[(events["effective_date"] >= w0) & (events["effective_date"] < w1 + pd.offsets.MonthBegin(1))]
    hikes = ev_w[(~ev_w["is_launch"]) & (ev_w["change_usd"] > 0)]

    kpi1 = f"{len(hikes)}" if len(hikes) else "0"
    kpi2 = f"+{hikes['change_pct'].median():.1f}%" if len(hikes) else "–"

    market = DATA["market"]
    m0 = market[market["month"] >= w0]
    if not m0.empty:
        kpi3 = f"{m0['market_index'].iloc[-1] / m0['market_index'].iloc[0] * 100 - 100:+.1f}%"
        kpi4 = f"{m0['cpi_index'].iloc[-1] / m0['cpi_index'].iloc[0] * 100 - 100:+.1f}%"
    else:
        kpi3 = kpi4 = "–"

    gap_w = gap[gap["service_name"].isin(services)]
    gap_w = gap_w[(gap_w["month"] >= w0) & (gap_w["month"] <= w1)]

    return (kpi1, kpi2, kpi3, kpi4,
            f"{w0:%b %Y} – {w1:%b %Y}",
            fig_dumbbell(summary),
            fig_timeline(ev_w, DATA["service_colors"]),
            fig_heatmap(ev_w),
            fig_hike_scatter(ev_w),
            fig_gap_lines(gap_w, DATA["service_colors"]),
            fig_gap_dumbbell(gap_w),
            fig_index(monthly, market, w0),
            fig_growth_vs_inflation(summary, monthly),
            )


# ---------------------------------------------------------------------------
# Linked views: clicking a chart point isolates its service
# ---------------------------------------------------------------------------
@callback(
    Output("services", "value"),
    Input("fig-q1", "clickData"), Input("fig-q2a", "clickData"),
    prevent_initial_call=True,
)
def isolate_service(q1_click, q2_click):
    ctx = dash.callback_context
    if not ctx.triggered:
        return no_update
    point = ctx.triggered[0]["value"]
    if not point or "points" not in point or not point["points"]:
        return no_update
    p = point["points"][0]
    # Q2 timeline uses service names on the y axis; Q1 uses "Service | Plan" ids.
    label = p.get("y") or p.get("label") or ""
    service = label.split(" | ")[0]
    return [service]


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------
@callback(
    Output("ckpi1", "children"), Output("ckpi2", "children"), Output("ckpi3", "children"),
    Output("fig-calc", "figure"),
    Input("calc-services", "value"), Input("calc-mode", "value"), Input("window", "value"),
)
def update_calc(services, mode, window):
    services = services or []
    w0, w1 = MONTHS[window[0]], MONTHS[window[1]]
    monthly = DATA["monthly"]
    monthly = monthly[(monthly["month"] >= w0) & (monthly["month"] <= w1)]
    fig = fig_calculator(monthly, services, mode, DATA["service_colors"])

    # KPI numbers recomputed with the same rules as fig_calculator
    mode_map = {"Cheapest ad-free": "no ads", "Cheapest with ads": "with ads"}
    pool = monthly[(~monthly["addon"]) & (~monthly["discontinued"])]
    pool = pool[pool["service_name"].isin(services)]
    if mode in mode_map:
        pool = pool[pool["tier"] == mode_map[mode]]
    if pool.empty:
        return "–", "–", "–", fig
    total = pool.groupby(["month", "service_name"])["price"].min().groupby("month").sum()
    last, first = float(total.iloc[-1]), float(total.iloc[0])
    jumps = total.diff().dropna()
    biggest = jumps.idxmax() if not jumps.empty and jumps.max() > 0 else None
    k3 = f"+${jumps.max():.2f} ({biggest:%b %Y})" if biggest is not None else "no jumps in window"
    delta = last - first
    return f"${last:.2f}", f"{'+' if delta >= 0 else '−'}${abs(delta):.2f}", k3, fig


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------
@callback(
    Output("services", "value", allow_duplicate=True),
    Output("tiers", "value"),
    Output("window", "value"),
    Output("advanced", "value"),
    Input("reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_):
    return ALL_SERVICES, ALL_TIERS, [0, len(MONTHS) - 1], ["y"]


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
