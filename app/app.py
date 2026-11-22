"""Streamflation — interactive dashboard (Plotly + Dash).

Run with:  python app/app.py   then open http://127.0.0.1:8050

Layout: one analysis window + tier/service filters drive every view (linked
views), a Q1–Q5 chart grid, and a "my subscriptions" cost calculator.
"""

from __future__ import annotations

import dash
from dash import Input, Output, State, callback, dcc, html, no_update
import pandas as pd

from figures import (TIER_COLORS, apply_theme, fig_calculator, fig_dumbbell, fig_gap_dumbbell,
                     fig_gap_lines, fig_growth_vs_inflation, fig_heatmap, fig_hike_scatter,
                     fig_timeline, fig_yoy_inflation, load_data)

DATA = load_data()
MONTHS = pd.date_range("2010-06-01", "2026-09-01", freq="MS")
ALL_SERVICES = sorted(DATA["events"]["service_name"].unique())
ALL_TIERS = ["no ads", "with ads", "add-on"]

app = dash.Dash(__name__, title="Streamflation — streaming price tracker 2010–2026")
server = app.server

GRAPH_CONFIG = {"displaylogo": False, "scrollZoom": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def card(title: str, chart_type: str, question: str, graph_id: str, details: str | None = None,
         span: int = 1) -> html.Div:
    """One analysis card: visible question line, optional collapsible 'how to read' text."""
    children = [
        html.Div(className="card-head", children=[
            html.H3(title),
            html.Span(chart_type, className="badge"),
        ]),
        html.P(question, className="q"),
    ]
    if details:
        children.append(html.Details(className="more", children=[
            html.Summary("How to read this chart"),
            html.P(details, className="details-body"),
        ], open=False))
    children.append(dcc.Graph(id=graph_id, config=GRAPH_CONFIG))
    return html.Div(className=f"card span{span}", children=children)


app.layout = html.Div(className="page", children=[
    dcc.Store(id="theme-store", data="light", storage_type="local"),
    dcc.Store(id="theme-class", data="light"),
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
        html.Button(id="theme-toggle", className="theme-toggle", n_clicks=0,
                    children=[html.Span(className="dot"),
                              html.Span("Dark mode", id="theme-toggle-label")]),
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
            # Q1 is full width: 20 plan rows on a categorical axis need the room,
            # and a half-width card would stretch its neighbour to a useless height.
            card("Q1 · Price rise since launch", "Dumbbell chart",
                 "How much has each plan's price risen since launch, and who leads?",
                 "fig-q1",
                 details=("Each row is one plan. The grey dot is its launch price, the blue dot "
                          "its latest price, and the connecting line is the increase. Rows are "
                          "sorted by percent growth, so the biggest riser is at the top. Hover for "
                          "exact dates plus the dollar and percent change; click a row to isolate "
                          "that service everywhere."),
                 span=2),
            card("Q2 · Do hikes cluster in time?", "Event dot plot (timeline)",
                 "Do competitors raise prices together, or independently?",
                 "fig-q2a",
                 details=("Each dot is one price change at its exact effective date, on the row of "
                          "the service that made it. Dot size is the size of the hike. Clustering "
                          "shows up as dots stacking vertically on the same date: four months "
                          "contain four or more simultaneous changes. Click a dot to isolate that "
                          "service.")),
            card("Q2 · Increases per service per year", "Heatmap",
                 "The same question as counts: which service hikes often, and in which years "
                 "did the whole market move?",
                 "fig-q2b",
                 details=("Rows are services, columns are years, and each cell counts price "
                          "increases, shaded from pale to dark. Dark horizontal bands mark a service "
                          "that raises prices often; dark vertical bands mark a year when most of "
                          "the market moved at once.")),
            card("Q3 · The price of going ad-free, service by service", "Small multiples",
                 "How much extra does it cost to remove ads, and is that premium growing?",
                 "fig-q3a",
                 details=("One panel per service, so the seven lines never overlap. Each panel plots "
                          "the cheapest no-ads plan minus the cheapest with-ads plan, every month, "
                          "with the latest value labelled in the corner. Panels share the same "
                          "vertical scale, so heights are directly comparable: a taller panel means a "
                          "bigger ad-free premium. Steps, not curves, because a price only changes on "
                          "a specific date. Six of seven services end higher than they started."),
                 span=2),
            card("Q3 · Today's ad-free premium", "Dumbbell chart",
                 "What does the ad-free upgrade cost right now, service by service?",
                 "fig-q3b",
                 details=("One row per service at the end of the selected window: the amber dot is "
                          "the cheapest with-ads plan, the blue dot the cheapest no-ads plan, and the "
                          "line between them is the premium, sorted largest at the top. This is the "
                          "ad-free premium chart above collapsed to its latest value, but shown in "
                          "absolute dollars so you can see what the upgrade actually costs."),
                 span=2),
            card("Q4 · Faster than inflation, year by year?", "Paired bar chart",
                 "In which years did streaming prices outpace the general cost of living?",
                 "fig-q4a",
                 details=("Each year compares two things side by side: how much streaming prices rose "
                          "that year, and how much US inflation rose that year. Because every year is "
                          "self-contained, one early price cut cannot distort later years the way it "
                          "does in a cumulative index. Red above grey means streaming outpaced "
                          "inflation; grey above red means it lagged, as in 2021 when inflation spiked. "
                          "The multiple above each pair says how many times inflation the streaming "
                          "increase was."),
                 span=2),
            card("Q4 · Every plan vs inflation", "Scatter plot with reference line",
                 "Which individual plans beat inflation over their own lifetime?",
                 "fig-q4b",
                 details=("Each bubble is one plan: horizontal position is inflation over that "
                          "plan's own lifetime, vertical position is its price growth over the same "
                          "window, and bubble size is how many months the window covers. Above the "
                          "dotted line the price outran inflation; below it the price lost ground in "
                          "real terms.")),
            card("Q5 · Small steps or big jumps?", "Bubble scatter plot",
                 "How do services raise prices: often and a little, or rarely and a lot?",
                 "fig-q5",
                 details=("Each bubble is a single price change. Horizontal position is months since "
                          "that plan's previous change, vertical position is the hike in percent, and "
                          "bubble size is the change in dollars. Frequent small increases crowd the "
                          "bottom left; rare large jumps sit high and right.")),
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
    Input("theme-store", "data"),
)
def update_all(services, tiers, window, advanced, theme):
    dark = theme == "dark"
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

    figs = [
        fig_dumbbell(summary),
        fig_timeline(ev_w, DATA["service_colors"], dark=dark),
        fig_heatmap(ev_w),
        fig_hike_scatter(ev_w, dark=dark),
        fig_gap_lines(gap_w, DATA["service_colors"], cols=4, dark=dark),
        fig_gap_dumbbell(gap_w, dark=dark),
        fig_yoy_inflation(DATA["yoy"], dark=dark),
        fig_growth_vs_inflation(summary, monthly, dark=dark),
    ]
    return (kpi1, kpi2, kpi3, kpi4,
            f"{w0:%b %Y} – {w1:%b %Y}",
            *[apply_theme(f, dark) for f in figs])


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
    Input("theme-store", "data"),
)
def update_calc(services, mode, window, theme):
    dark = theme == "dark"
    services = services or []
    w0, w1 = MONTHS[window[0]], MONTHS[window[1]]
    monthly = DATA["monthly"]
    monthly = monthly[(monthly["month"] >= w0) & (monthly["month"] <= w1)]
    fig = apply_theme(fig_calculator(monthly, services, mode, DATA["service_colors"], dark=dark), dark)

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
# Theme toggle — flips the store, swaps the body class and relabels the button
# ---------------------------------------------------------------------------
app.clientside_callback(
    """
    function(n_clicks, current) {
        if (!n_clicks) { return [window.dash_clientside.no_update,
                                 window.dash_clientside.no_update,
                                 window.dash_clientside.no_update]; }
        const next = (current === "dark") ? "light" : "dark";
        document.body.classList.toggle("dark", next === "dark");
        return [next, next, next === "dark" ? "Light mode" : "Dark mode"];
    }
    """,
    Output("theme-store", "data", allow_duplicate=True),
    Output("theme-class", "data", allow_duplicate=True),
    Output("theme-toggle-label", "children"),
    Input("theme-toggle", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Apply the saved theme on first load (the toggle sets the class on click, but a
# page reload starts with a bare <body>, so the store value has to be re-applied)
# ---------------------------------------------------------------------------
app.clientside_callback(
    """
    function(theme) {
        if (!theme) { return window.dash_clientside.no_update; }
        document.body.classList.toggle("dark", theme === "dark");
        return theme === "dark" ? "Light mode" : "Dark mode";
    }
    """,
    Output("theme-toggle-label", "children", allow_duplicate=True),
    Input("theme-store", "data"),
    prevent_initial_call="initial_duplicate",
)


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
