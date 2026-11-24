"""Plotly figures for the Northwind analysis webpage."""

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

BLUE = "#2f6db5"
RED = "#c4473a"
GREY = "#8a8f98"
AMBER = "#d08c1f"
GREEN = "#3c8d5a"

LAYOUT = dict(
    template="simple_white",
    font=dict(family="Inter, -apple-system, Segoe UI, sans-serif", size=13, color="#222"),
    margin=dict(l=70, r=30, t=60, b=60),
    hoverlabel=dict(font_size=12),
)


def fig_monthly_revenue(monthly):
    """Plot monthly revenue as a line chart.

    Args:
        monthly (pandas.DataFrame): Output of ``monthly_revenue``.

    Returns:
        plotly.graph_objects.Figure: Revenue by month.
    """
    fig = go.Figure(
        go.Scatter(
            x=monthly["Month"],
            y=monthly["Revenue"],
            mode="lines+markers",
            line=dict(color=BLUE, width=2.5),
            hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>",
        )
    )
    fig.update_layout(
        **LAYOUT,
        height=320,
        title="Monthly revenue, Jul 1996 – Apr 1998 (May 1998 excluded: partial month)",
    )
    fig.update_yaxes(title="Revenue (USD, after discounts)", tickprefix="$", tickformat=",.0f")
    fig.update_xaxes(title="Order month", dtick="M3", tickformat="%b %Y")
    return fig


def fig_market_growth(growth):
    """Plot revenue change by country as horizontal bars.

    Args:
        growth (pandas.DataFrame): Output of ``market_growth``.

    Returns:
        plotly.graph_objects.Figure: One bar per country; red bars are
        declines.
    """
    colors = [RED if v < 0 else BLUE for v in growth["Change"]]
    fig = go.Figure(
        go.Bar(
            x=growth["Change"],
            y=growth["Country"],
            orientation="h",
            marker_color=colors,
            customdata=np.stack([growth["Rev1997"], growth["Rev1998"]], axis=1),
            hovertemplate=(
                "%{y}<br>Jan–Apr 1997: $%{customdata[0]:,.0f}"
                "<br>Jan–Apr 1998: $%{customdata[1]:,.0f}"
                "<br>Change: $%{x:,.0f}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **LAYOUT,
        height=560,
        title="Change in revenue by customer country, Jan–Apr 1998 vs Jan–Apr 1997",
    )
    fig.update_xaxes(title="Revenue change (USD)", tickprefix="$", tickformat=",.0f",
                     zeroline=True, zerolinecolor="#444")
    fig.update_yaxes(title=None)
    return fig


def fig_pareto(concentration, flagged_ids):
    """Plot ranked customer revenue with a cumulative share line.

    Args:
        concentration (pandas.DataFrame): Output of
            ``customer_concentration``.
        flagged_ids (set[str]): Customer IDs whose bars are drawn red.

    Returns:
        plotly.graph_objects.Figure: Revenue bars on the left axis and
        cumulative share (%) on the right axis.
    """
    colors = [RED if cid in flagged_ids else BLUE for cid in concentration["CustomerID"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_bar(
        x=concentration["Rank"],
        y=concentration["Revenue"],
        marker_color=colors,
        customdata=concentration[["CompanyName", "Country"]].values,
        hovertemplate="#%{x} %{customdata[0]} (%{customdata[1]})<br>$%{y:,.0f}<extra></extra>",
        name="Customer revenue",
    )
    fig.add_scatter(
        x=concentration["Rank"],
        y=concentration["CumulativeSharePct"],
        mode="lines",
        line=dict(color="#222", width=2),
        name="Cumulative share of revenue",
        hovertemplate="Top %{x} customers: %{y:.1f}% of revenue<extra></extra>",
        secondary_y=True,
    )
    fig.add_hline(y=80, line_dash="dot", line_color=GREY, secondary_y=True)
    fig.update_layout(
        **LAYOUT,
        height=420,
        title="Revenue by customer, ranked (red = lapsed top-25 account, see table)",
        legend=dict(orientation="h", y=-0.22, x=0),
    )
    fig.update_xaxes(title="Customer rank by total revenue (Jul 1996 – May 1998)")
    fig.update_yaxes(title="Revenue (USD)", tickprefix="$", tickformat=",.0f", secondary_y=False)
    fig.update_yaxes(title="Cumulative share (%)", range=[0, 102], secondary_y=True)
    return fig


def fig_discount_box(standard, by_level):
    """Plot relative order quantity by discount level.

    Args:
        standard (pandas.DataFrame): Kept lines from
            ``discount_effect``.
        by_level (pandas.DataFrame): Per-level summary with
            intervals, from ``add_level_cis``.

    Returns:
        plotly.graph_objects.Figure: One box per discount level with a
        marker and 95% interval at each level's mean.
    """
    fig = go.Figure()
    for pct in sorted(standard["DiscountPct"].unique()):
        subset = standard[standard["DiscountPct"] == pct]
        fig.add_box(
            y=subset["RelativeQty"],
            name=f"{pct}%",
            marker_color=GREY if pct == 0 else BLUE,
            boxpoints=False,
            showlegend=False,
            hoverinfo="y",
        )
    fig.add_scatter(
        x=[f"{p}%" for p in by_level["DiscountPct"]],
        y=by_level["MeanRelativeQty"],
        error_y=dict(
            type="data",
            symmetric=False,
            array=by_level["MeanCIHigh"] - by_level["MeanRelativeQty"],
            arrayminus=by_level["MeanRelativeQty"] - by_level["MeanCILow"],
            color="#222",
            thickness=1.5,
        ),
        mode="markers+text",
        marker=dict(symbol="diamond", size=11, color=AMBER, line=dict(color="#222", width=1)),
        text=[f"{v:.2f}" for v in by_level["MeanRelativeQty"]],
        textposition="top center",
        name="Mean with bootstrap 95% CI",
        hovertemplate="Mean relative quantity: %{y:.2f}<extra></extra>",
    )
    fig.update_layout(
        **LAYOUT,
        height=440,
        title="Quantity per order line relative to the same product's undiscounted average",
        legend=dict(orientation="h", y=-0.2, x=0),
    )
    fig.update_yaxes(title="Relative quantity (1.0 = product's undiscounted mean)",
                     range=[0, 3.5])
    fig.update_xaxes(title="Discount on the order line")
    return fig


def _rate_bar(fig, table, label_col, col, color):
    """Add a late-rate bar trace with confidence intervals to a subplot.

    Args:
        fig (plotly.graph_objects.Figure): Figure with a 1x2
            subplot grid.
        table (pandas.DataFrame): Output of ``late_rates``.
        label_col (str): Column holding the bar labels.
        col (int): Subplot column, 1 or 2.
        color (str | list[str]): Bar colour, or one colour per bar.

    Returns:
        None. Adds the trace to ``fig`` in place.
    """
    fig.add_bar(
        x=table[label_col],
        y=table["LateRatePct"],
        marker_color=color,
        error_y=dict(
            type="data",
            symmetric=False,
            array=table["CIHighPct"] - table["LateRatePct"],
            arrayminus=table["LateRatePct"] - table["CILowPct"],
            color="#444",
        ),
        customdata=table[["LateOrders", "Orders", "AvgLeadDays"]].values,
        hovertemplate=(
            "%{x}<br>Late: %{customdata[0]} of %{customdata[1]} (%{y:.1f}%)"
            "<br>Avg days to ship: %{customdata[2]:.1f}<extra></extra>"
        ),
        showlegend=False,
        row=1,
        col=col,
    )


def fig_late_rates(by_window, by_shipper):
    """Plot late rates by delivery window and by shipper side by side.

    Args:
        by_window (pandas.DataFrame): ``late_rates`` grouped by
            ``WindowDays``.
        by_shipper (pandas.DataFrame): ``late_rates`` grouped by
            ``Shipper``.

    Returns:
        plotly.graph_objects.Figure: Two bar panels with 95% interval
        error bars.
    """
    by_window = by_window.copy()
    by_window["Label"] = by_window["WindowDays"].astype(str) + "-day deadline"
    fig = make_subplots(
        rows=1,
        cols=2,
        shared_yaxes=True,
        subplot_titles=("By promised delivery window", "By shipper"),
        horizontal_spacing=0.06,
    )
    _rate_bar(fig, by_window, "Label", 1, [RED, BLUE, BLUE])
    _rate_bar(fig, by_shipper, "Shipper", 2, GREY)
    fig.update_layout(
        **LAYOUT,
        height=420,
        title="Share of shipped orders that missed the required date (bars: 95% Wilson interval)",
    )
    fig.update_yaxes(title="Late orders (%)", ticksuffix="%", row=1, col=1)
    return fig


def fig_lead_time(orders):
    """Plot days from order to shipment for each promised window.

    Args:
        orders (pandas.DataFrame): Orders from ``build_orders``.

    Returns:
        plotly.graph_objects.Figure: Horizontal box plots for the 14-,
        28- and 42-day windows, with a dotted line at each deadline.
    """
    shipped = orders[orders["ShippedDate"].notna()]
    fig = go.Figure()
    for window, color in [(14, RED), (28, BLUE), (42, GREEN)]:
        subset = shipped[shipped["WindowDays"] == window]
        fig.add_box(
            x=subset["LeadDays"],
            name=f"{window}-day deadline (n={len(subset)})",
            marker_color=color,
            boxpoints="outliers",
            orientation="h",
        )
        fig.add_vline(x=window, line_dash="dot", line_color=color)
    fig.update_layout(
        **LAYOUT,
        height=330,
        showlegend=False,
        title="Days from order to shipment, by promised window (dotted lines = deadline)",
    )
    fig.update_xaxes(title="Days from order date to ship date", range=[0, 45])
    return fig


def fig_inventory(cover):
    """Plot months of cover against sales rate for active products.

    Products with no recent sales are left out, and cover is clipped to
    0.03-30 months so it fits the log axis.

    Args:
        cover (pandas.DataFrame): Product table from
            ``inventory_cover``.

    Returns:
        plotly.graph_objects.Figure: Scatter coloured by stock status,
        bubble size scaled to recent revenue.
    """
    active = cover[~cover["Discontinued"] & (cover["UnitsPerMonth"] > 0)].copy()
    active["PlotCover"] = active["MonthsCoverInclOnOrder"].clip(lower=0.03, upper=30)
    palette = {
        "Stockout risk (<1 month incl. on order)": RED,
        "Healthy": GREY,
        "Overstocked (>3 months on hand)": AMBER,
    }
    fig = go.Figure()
    for status, color in palette.items():
        subset = active[active["Status"] == status]
        fig.add_scatter(
            x=subset["UnitsPerMonth"],
            y=subset["PlotCover"],
            mode="markers",
            name=f"{status} ({len(subset)})",
            marker=dict(
                color=color,
                size=np.sqrt(subset["RecentRevenue"].clip(lower=1)) / 8 + 5,
                line=dict(color="#fff", width=0.5),
                opacity=0.85,
            ),
            customdata=subset[
                ["ProductName", "UnitsInStock", "UnitsOnOrder", "RecentRevenue"]
            ].values,
            hovertemplate=(
                "%{customdata[0]}<br>Sells %{x:.0f} units/month"
                "<br>In stock %{customdata[1]}, on order %{customdata[2]}"
                "<br>Cover: %{y:.2f} months<br>6-mo revenue $%{customdata[3]:,.0f}"
                "<extra></extra>"
            ),
        )
    fig.add_hline(y=1, line_dash="dot", line_color=RED)
    fig.update_layout(
        **LAYOUT,
        height=470,
        title="Inventory cover vs. sales rate for active products (bubble size = 6-month revenue)",
        legend=dict(orientation="h", y=-0.22, x=0),
    )
    fig.update_xaxes(title="Units sold per month (Nov 1997 – Apr 1998 average)")
    fig.update_yaxes(title="Months of cover: (in stock + on order) ÷ monthly units",
                     type="log", tickvals=[0.1, 0.25, 0.5, 1, 2, 5, 10, 25])
    return fig
