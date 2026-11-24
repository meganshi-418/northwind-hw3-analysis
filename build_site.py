"""Rebuild all tables, charts and the webpage from Northwind data."""

import argparse
import json
from pathlib import Path
from string import Template

from northwind_analysis import analysis, figures
from northwind_analysis.data import DEFAULT_PATH, build_order_lines, build_orders, load_tables

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "templates" / "index.html"


def money(value):
    """Format an amount as whole US dollars.

    Args:
        value (float): Amount in USD.

    Returns:
        str: Amount such as ``"$1,234"``.
    """
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def pct(value, digits=0):
    """Format a percentage value as a string.

    Args:
        value (float): Percentage already scaled to 0-100.
        digits (int): Decimal places to show.

    Returns:
        str: Value with a ``%`` sign, such as ``"12.5%"``.
    """
    return f"{value:.{digits}f}%"


def fig_html(fig, div_id):
    """Render a figure as an HTML fragment without bundled plotly.js.

    Args:
        fig (plotly.graph_objects.Figure): Figure to render.
        div_id (str): HTML id for the chart's container div.

    Returns:
        str: HTML ``<div>`` and script for the chart.
    """
    return fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config={"displaylogo": False, "responsive": True},
    )


def html_table(df, columns, formats, header=None):
    """Render selected DataFrame columns as an HTML table.

    Cell values are inserted as-is, without HTML escaping.

    Args:
        df (pandas.DataFrame): Rows to show, in display order.
        columns (list[str]): Columns to include, in order.
        formats (dict[str, Callable[[Any], str]]): Formatter per column;
            columns without one use ``str``.
        header (list[str] | None): Header labels; None uses ``columns``.

    Returns:
        str: ``<table>`` markup.
    """
    header = header or columns
    head = "".join(f"<th>{h}</th>" for h in header)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{formats.get(c, str)(row[c])}</td>" for c in columns)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def run(data_path, out_dir, site_dir):
    """Run the analysis and write the CSVs, summary JSON and webpage.

    Args:
        data_path (pathlib.Path): Northwind Excel workbook.
        out_dir (pathlib.Path): Folder for CSV tables and
            ``summary.json``; created if missing.
        site_dir (pathlib.Path): Folder for ``index.html``; created if
            missing.

    Returns:
        dict[str, float | int]: Headline figures, as written to
        ``summary.json``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    site_dir.mkdir(parents=True, exist_ok=True)

    tables = load_tables(data_path)
    lines = build_order_lines(tables)
    orders = build_orders(tables)

    # Q1: market growth
    monthly = analysis.monthly_revenue(lines)
    growth = analysis.market_growth(lines)
    rev97, rev98 = growth["Rev1997"].sum(), growth["Rev1998"].sum()
    top_growth = growth.sort_values("Change", ascending=False)
    decliners = growth[growth["Change"] < 0].sort_values("Change")

    # Q2: concentration and lapsed accounts
    concentration = analysis.customer_concentration(lines)
    flagged = analysis.at_risk_customers(orders, concentration)
    n_for_80 = int((concentration["CumulativeSharePct"] < 80).sum() + 1)
    top3_share = concentration["CumulativeSharePct"].iloc[2]
    top10_share = concentration["CumulativeSharePct"].iloc[9]
    key_lapsed = flagged[flagged["Rank"] <= 25]

    # Q3: discounts
    standard, by_level = analysis.discount_effect(lines)
    by_level = analysis.add_level_cis(standard, by_level)
    slope, slope_lo, slope_hi = analysis.discount_slope(standard)
    wc_any = analysis.within_customer_comparison(standard, [0], [5, 10])
    wc_deep = analysis.within_customer_comparison(standard, [5, 10], [15, 20, 25])
    wc_5v10 = analysis.within_customer_comparison(standard, [5], [10])
    cap10_savings = analysis.discount_cap_savings(lines, cap=0.10)
    total_discount = lines["DiscountAmount"].sum()
    gross = lines["GrossRevenue"].sum()
    cap_savings = analysis.discount_cap_savings(lines, cap=0.05)
    level = by_level.set_index("DiscountPct")
    deep_discount_share = level.loc[[15, 20, 25], "DiscountGiven"].sum() / total_discount * 100

    # Q4: late deliveries
    by_window = analysis.late_rates(orders, "WindowDays")
    by_shipper = analysis.late_rates(orders, "Shipper")
    shipped = orders[orders["ShippedDate"].notna()]
    median_lead = shipped.groupby("WindowDays")["LeadDays"].median()
    window = by_window.set_index("WindowDays")
    rush_late_share = window.loc[14, "LateOrders"] / window["LateOrders"].sum() * 100

    # Q5: inventory
    cover, months = analysis.inventory_cover(tables, lines)
    active = cover[~cover["Discontinued"]]
    at_risk = active[active["Status"].str.startswith("Stockout")].sort_values(
        "RecentRevenue", ascending=False
    )
    overstock = active[active["Status"].str.startswith("Overstocked")]
    at_risk_rev_share = at_risk["RecentRevenue"].sum() / active["RecentRevenue"].sum() * 100
    top_risk = at_risk.iloc[0]
    no_order_at_risk = int((at_risk["UnitsOnOrder"] == 0).sum())

    # Save reproducible tables
    monthly.to_csv(out_dir / "q1_monthly_revenue.csv", index=False)
    growth.to_csv(out_dir / "q1_country_growth_janapr.csv", index=False)
    concentration.to_csv(out_dir / "q2_customer_concentration.csv", index=False)
    flagged.to_csv(out_dir / "q2_lapsed_customers.csv", index=False)
    by_level.to_csv(out_dir / "q3_discount_levels.csv", index=False)
    by_window.to_csv(out_dir / "q4_late_by_window.csv", index=False)
    by_shipper.to_csv(out_dir / "q4_late_by_shipper.csv", index=False)
    cover.to_csv(out_dir / "q5_inventory_cover.csv", index=False)

    summary = {
        "total_revenue": round(float(lines["Revenue"].sum()), 2),
        "orders": int(orders["OrderID"].nunique()),
        "customers_with_orders": int(lines["CustomerID"].nunique()),
        "janapr_1997": round(float(rev97), 2),
        "janapr_1998": round(float(rev98), 2),
        "top3_share_pct": round(float(top3_share), 1),
        "top10_share_pct": round(float(top10_share), 1),
        "customers_for_80pct": n_for_80,
        "total_discount": round(float(total_discount), 2),
        "discount_cap_5pct_savings": round(float(cap_savings), 2),
        "discount_cap_10pct_savings": round(float(cap10_savings), 2),
        "discount_slope_per_pt": round(slope, 4),
        "discount_slope_ci": [round(slope_lo, 4), round(slope_hi, 4)],
        "within_customer_0_vs_5_10": wc_any,
        "within_customer_5_10_vs_15_25": wc_deep,
        "within_customer_5_vs_10": wc_5v10,
        "late_rate_14d_pct": round(float(window.loc[14, "LateRatePct"]), 1),
        "late_rate_28d_pct": round(float(window.loc[28, "LateRatePct"]), 1),
        "stockout_risk_products": int(len(at_risk)),
        "active_products": int(len(active)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    flagged_ids = set(key_lapsed["CustomerID"])
    fmt_money = money
    fmt_int = lambda v: f"{int(v):,}"
    fmt_date = lambda v: v.strftime("%b %d, %Y")

    values = dict(
        total_revenue=money(summary["total_revenue"]),
        n_orders=f"{summary['orders']:,}",
        n_lines=f"{len(lines):,}",
        n_customers=summary["customers_with_orders"],
        n_customers_listed=len(tables["Customers"]),
        n_products=len(tables["Products"]),
        # Q1
        fig_monthly=fig_html(figures.fig_monthly_revenue(monthly), "fig-monthly"),
        fig_growth=fig_html(figures.fig_market_growth(growth), "fig-growth"),
        rev97=money(rev97),
        rev98=money(rev98),
        growth_pct=pct((rev98 / rev97 - 1) * 100),
        g1_name=top_growth.iloc[0]["Country"],
        g1_change=money(top_growth.iloc[0]["Change"]),
        g2_name=top_growth.iloc[1]["Country"],
        g2_change=money(top_growth.iloc[1]["Change"]),
        g3_name=top_growth.iloc[2]["Country"],
        g3_change=money(top_growth.iloc[2]["Change"]),
        top3_growth_share=pct(top_growth.head(3)["ShareOfGrowthPct"].sum()),
        decliner_list=", ".join(
            f"{r.Country} ({money(r.Change)})" for r in decliners.itertuples()
        ),
        n_decliners=len(decliners),
        # Q2
        fig_pareto=fig_html(figures.fig_pareto(concentration, flagged_ids), "fig-pareto"),
        top3_share=pct(top3_share),
        top10_share=pct(top10_share),
        n_for_80=n_for_80,
        lapsed_table=html_table(
            flagged,
            ["CompanyName", "Country", "Rank", "Revenue", "Orders", "AvgGapDays",
             "LastOrder", "DaysSinceLast"],
            {"Revenue": fmt_money, "Rank": fmt_int, "Orders": fmt_int,
             "AvgGapDays": lambda v: f"{v:.0f}", "LastOrder": fmt_date,
             "DaysSinceLast": fmt_int},
            ["Customer", "Country", "Revenue rank", "Lifetime revenue", "Orders",
             "Usual gap (days)", "Last order", "Days silent"],
        ),
        lapsed_top_name=flagged.iloc[0]["CompanyName"],
        lapsed_top_rank=int(flagged.iloc[0]["Rank"]),
        lapsed_top_rev=money(flagged.iloc[0]["Revenue"]),
        lapsed_top_gap=f"{flagged.iloc[0]['AvgGapDays']:.0f}",
        lapsed_top_silent=int(flagged.iloc[0]["DaysSinceLast"]),
        lapsed_total=money(flagged["Revenue"].sum()),
        n_lapsed=len(flagged),
        # Q3
        fig_discount=fig_html(figures.fig_discount_box(standard, by_level), "fig-discount"),
        discount_table=html_table(
            by_level.assign(
                MeanCI=[f"{lo:.2f}–{hi:.2f}" for lo, hi in
                        zip(by_level["MeanCILow"], by_level["MeanCIHigh"])]
            ),
            ["DiscountPct", "Lines", "MeanRelativeQty", "MeanCI", "MedianRelativeQty",
             "DiscountGiven"],
            {"DiscountPct": lambda v: f"{int(v)}%", "Lines": fmt_int,
             "MeanRelativeQty": lambda v: f"{v:.2f}",
             "MedianRelativeQty": lambda v: f"{v:.2f}",
             "DiscountGiven": fmt_money},
            ["Discount", "Order lines", "Mean relative qty", "95% CI of mean",
             "Median relative qty", "Revenue given away"],
        ),
        total_discount=money(total_discount),
        discount_of_gross=pct(total_discount / gross * 100, 1),
        n_discount_lines=f"{int((lines['Discount'] > 0).sum()):,}",
        rq5=f"{level.loc[5, 'MeanRelativeQty']:.2f}",
        rq10=f"{level.loc[10, 'MeanRelativeQty']:.2f}",
        rq25=f"{level.loc[25, 'MeanRelativeQty']:.2f}",
        deep_discount_share=pct(deep_discount_share),
        cap_savings=money(cap_savings),
        cap10_savings=money(cap10_savings),
        cap10_savings_pct=pct(cap10_savings / lines["Revenue"].sum() * 100, 1),
        cap_gap=money(cap_savings - cap10_savings),
        ci5=f"{level.loc[5, 'MeanCILow']:.2f}–{level.loc[5, 'MeanCIHigh']:.2f}",
        ci10=f"{level.loc[10, 'MeanCILow']:.2f}–{level.loc[10, 'MeanCIHigh']:.2f}",
        slope=f"{slope:+.3f}",
        slope_ci=f"{slope_lo:+.3f} to {slope_hi:+.3f}",
        wc_deep_n=wc_deep["customers"],
        wc_deep_diff=f"{wc_deep['median_diff']:+.2f}",
        wc_deep_share=pct(wc_deep["share_higher"] * 100),
        wc_any_n=wc_any["customers"],
        wc_any_diff=f"{wc_any['median_diff']:+.2f}",
        wc_any_share=pct(wc_any["share_higher"] * 100),
        wc_5v10_n=wc_5v10["customers"],
        wc_5v10_diff=f"{wc_5v10['median_diff']:+.2f}",
        wc_5v10_share=pct(wc_5v10["share_higher"] * 100),
        cap_savings_pct=pct(cap_savings / lines["Revenue"].sum() * 100, 1),
        n_odd_discounts=int((~lines["Discount"].round(2).isin(analysis.STANDARD_DISCOUNTS)).sum()),
        # Q4
        fig_late=fig_html(figures.fig_late_rates(by_window, by_shipper), "fig-late"),
        fig_lead=fig_html(figures.fig_lead_time(orders), "fig-lead"),
        n_shipped=len(shipped),
        n_unshipped=int(orders["ShippedDate"].isna().sum()),
        n_late=int(shipped["Late"].sum()),
        late_overall=pct(shipped["Late"].mean() * 100, 1),
        late14=pct(window.loc[14, "LateRatePct"], 1),
        late14_lo=pct(window.loc[14, "CILowPct"]),
        late14_hi=pct(window.loc[14, "CIHighPct"]),
        late28=pct(window.loc[28, "LateRatePct"], 1),
        n14=int(window.loc[14, "Orders"]),
        n14_share=pct(window.loc[14, "Orders"] / len(shipped) * 100),
        rush_late_share=pct(rush_late_share),
        med14=f"{median_lead.loc[14]:.1f}",
        med28=f"{median_lead.loc[28]:.1f}",
        avg14=f"{window.loc[14, 'AvgLeadDays']:.1f}",
        avg28=f"{window.loc[28, 'AvgLeadDays']:.1f}",
        ship_min=pct(by_shipper["LateRatePct"].min(), 1),
        ship_max=pct(by_shipper["LateRatePct"].max(), 1),
        # Q5
        fig_inventory=fig_html(figures.fig_inventory(cover), "fig-inventory"),
        inv_months=months,
        n_at_risk=len(at_risk),
        n_active=len(active),
        at_risk_rev_share=pct(at_risk_rev_share),
        no_order_at_risk=no_order_at_risk,
        top_risk_name=top_risk["ProductName"],
        top_risk_rev=money(top_risk["RecentRevenue"]),
        top_risk_stock=int(top_risk["UnitsInStock"]),
        top_risk_rate=f"{top_risk['UnitsPerMonth']:.0f}",
        n_overstock=len(overstock),
        inventory_table=html_table(
            at_risk.head(10),
            ["ProductName", "UnitsPerMonth", "UnitsInStock", "UnitsOnOrder",
             "ReorderLevel", "MonthsCoverInclOnOrder", "RecentRevenue"],
            {"UnitsPerMonth": lambda v: f"{v:.0f}", "UnitsInStock": fmt_int,
             "UnitsOnOrder": fmt_int, "ReorderLevel": fmt_int,
             "MonthsCoverInclOnOrder": lambda v: f"{v:.2f}", "RecentRevenue": fmt_money},
            ["Product", "Units / month", "In stock", "On order", "Reorder level",
             "Months of cover", f"Revenue, last {months} months"],
        ),
    )

    page = Template(TEMPLATE.read_text(encoding="utf-8")).substitute(values)
    (site_dir / "index.html").write_text(page, encoding="utf-8")
    return summary


def main():
    """Parse command-line options and rebuild the site.

    Args:
        None.

    Returns:
        None. Prints the headline figures as JSON.
    """
    parser = argparse.ArgumentParser(description="Rebuild the Northwind analysis site.")
    parser.add_argument("--data", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs")
    parser.add_argument("--site", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    summary = run(args.data, args.out, args.site)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
