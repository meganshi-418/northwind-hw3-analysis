"""Calculations behind the five Northwind business questions."""

import numpy as np
import pandas as pd

from .data import DATA_END, LAST_FULL_MONTH_END

STANDARD_DISCOUNTS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.25]


def monthly_revenue(lines):
    """Sum revenue by order month, through April 1998.

    Args:
        lines (pandas.DataFrame): Output of ``build_order_lines``.

    Returns:
        pandas.DataFrame: ``Month`` (first day of the month) and
        ``Revenue`` in USD, one row per month.
    """
    full = lines[lines["OrderDate"] <= LAST_FULL_MONTH_END]
    monthly = (
        full.groupby(full["OrderDate"].dt.to_period("M"))["Revenue"].sum().reset_index()
    )
    monthly["Month"] = monthly["OrderDate"].dt.to_timestamp()
    return monthly[["Month", "Revenue"]]


def market_growth(lines, months=(1, 2, 3, 4)):
    """Compare country revenue for the same months of 1997 and 1998.

    Args:
        lines (pandas.DataFrame): Output of ``build_order_lines``.
        months (tuple[int, ...]): Calendar months (1-12) compared
            in both years.

    Returns:
        pandas.DataFrame: One row per customer country with ``Rev1997``,
        ``Rev1998``, ``Change`` (USD), ``GrowthPct`` (NaN when 1997
        revenue is zero) and ``ShareOfGrowthPct``, sorted by ``Change``
        ascending.
    """
    window = lines[lines["OrderDate"].dt.month.isin(months)]
    window = window[window["OrderDate"].dt.year.isin([1997, 1998])]
    table = (
        window.pivot_table(
            index="Country",
            columns=window["OrderDate"].dt.year,
            values="Revenue",
            aggfunc="sum",
        )
        .reindex(columns=[1997, 1998])
        .fillna(0.0)
    )
    table.columns = ["Rev1997", "Rev1998"]
    table["Change"] = table["Rev1998"] - table["Rev1997"]
    table["GrowthPct"] = np.where(
        table["Rev1997"] > 0, table["Change"] / table["Rev1997"] * 100, np.nan
    )
    table["ShareOfGrowthPct"] = table["Change"] / table["Change"].sum() * 100
    return table.sort_values("Change").reset_index()


def customer_concentration(lines):
    """Rank customers by total revenue with cumulative share.

    Args:
        lines (pandas.DataFrame): Output of ``build_order_lines``.

    Returns:
        pandas.DataFrame: One row per customer, highest revenue first,
        with ``Revenue``, ``Rank`` (1 = largest) and
        ``CumulativeSharePct``.
    """
    revenue = (
        lines.groupby(["CustomerID", "CompanyName", "Country"])["Revenue"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    revenue["Rank"] = np.arange(1, len(revenue) + 1)
    revenue["CumulativeSharePct"] = revenue["Revenue"].cumsum() / revenue["Revenue"].sum() * 100
    return revenue


def at_risk_customers(orders, concentration, min_orders=3, gap_multiple=2.0):
    """Flag customers silent far longer than their usual order gap.

    The usual gap is the span from first to last order divided by the
    number of gaps. Silence is measured up to ``DATA_END`` (1998-05-06).

    Args:
        orders (pandas.DataFrame): Orders from ``build_orders``.
        concentration (pandas.DataFrame): Output of
            ``customer_concentration``.
        min_orders (int): Fewest orders a customer needs to be flagged.
        gap_multiple (float): Flag when days since the last order exceed
            this multiple of the usual gap.

    Returns:
        pandas.DataFrame: Flagged customers with ``Orders``,
        ``AvgGapDays``, ``DaysSinceLast`` and ``GapMultiple`` added,
        highest revenue first.
    """
    stats = orders.groupby("CustomerID")["OrderDate"].agg(
        Orders="count", FirstOrder="min", LastOrder="max"
    )
    stats["AvgGapDays"] = (stats["LastOrder"] - stats["FirstOrder"]).dt.days / (
        stats["Orders"] - 1
    ).clip(lower=1)
    stats["DaysSinceLast"] = (DATA_END - stats["LastOrder"]).dt.days
    stats["GapMultiple"] = stats["DaysSinceLast"] / stats["AvgGapDays"]
    merged = concentration.merge(stats.reset_index(), on="CustomerID")
    flagged = merged[
        (merged["Orders"] >= min_orders) & (merged["GapMultiple"] > gap_multiple)
    ]
    return flagged.sort_values("Revenue", ascending=False).reset_index(drop=True)


def discount_effect(lines):
    """Measure relative order size at each standard discount level.

    Each line's quantity is divided by the mean undiscounted quantity of
    the same product, so 1.0 is a typical order for that product. Lines
    with discounts not in ``STANDARD_DISCOUNTS`` are dropped.

    Args:
        lines (pandas.DataFrame): Output of ``build_order_lines``.

    Returns:
        tuple[pandas.DataFrame, pandas.DataFrame]: The kept lines with
        ``RelativeQty`` and ``DiscountPct`` added; and one row per
        discount percentage with line count, mean and median relative
        quantity, and ``DiscountGiven`` in USD.
    """
    standard = lines[lines["Discount"].round(2).isin(STANDARD_DISCOUNTS)].copy()
    baseline = (
        standard[standard["Discount"] == 0].groupby("ProductID")["Quantity"].mean()
    )
    standard["BaselineQty"] = standard["ProductID"].map(baseline)
    standard = standard.dropna(subset=["BaselineQty"])
    standard["RelativeQty"] = standard["Quantity"] / standard["BaselineQty"]
    standard["DiscountPct"] = (standard["Discount"] * 100).round().astype(int)

    by_level = (
        standard.groupby("DiscountPct")
        .agg(
            Lines=("OrderID", "count"),
            MedianRelativeQty=("RelativeQty", "median"),
            MeanRelativeQty=("RelativeQty", "mean"),
            DiscountGiven=("DiscountAmount", "sum"),
        )
        .reset_index()
    )
    return standard, by_level


def discount_cap_savings(lines, cap=0.05):
    """Compute the discount dollars a cap would have kept.

    Assumes order quantities would not change under the cap.

    Args:
        lines (pandas.DataFrame): Output of ``build_order_lines``.
        cap (float): Maximum discount as a fraction (0.05 = 5%).

    Returns:
        float: Discount given above ``cap``, in USD.
    """
    deep = lines[lines["Discount"] > cap]
    return float((deep["GrossRevenue"] * (deep["Discount"] - cap)).sum())


def wilson_interval(successes, n, z=1.96):
    """Compute the Wilson score interval for a proportion.

    Args:
        successes (int): Number of positive outcomes.
        n (int): Number of trials.
        z (float): Normal quantile; 1.96 gives a 95% interval.

    Returns:
        tuple[float, float]: Lower and upper bounds as fractions, or
        ``(nan, nan)`` when ``n`` is 0.
    """
    if n == 0:
        return np.nan, np.nan
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return centre - half, centre + half


def late_rates(orders, by):
    """Summarise late shipments for each group of shipped orders.

    Args:
        orders (pandas.DataFrame): Orders from ``build_orders``.
        by (str | list[str]): Column(s) to group by, e.g. ``"Shipper"``.

    Returns:
        pandas.DataFrame: One row per group with order and late counts,
        mean lead days and freight, ``LateRatePct`` and its 95% Wilson
        interval (``CILowPct``, ``CIHighPct``).
    """
    shipped = orders[orders["ShippedDate"].notna()]
    table = (
        shipped.groupby(by)
        .agg(
            Orders=("OrderID", "count"),
            LateOrders=("Late", "sum"),
            AvgLeadDays=("LeadDays", "mean"),
            AvgFreight=("Freight", "mean"),
        )
        .reset_index()
    )
    table["LateRatePct"] = table["LateOrders"] / table["Orders"] * 100
    bounds = [wilson_interval(k, n) for k, n in zip(table["LateOrders"], table["Orders"])]
    table["CILowPct"] = [lo * 100 for lo, _ in bounds]
    table["CIHighPct"] = [hi * 100 for _, hi in bounds]
    return table


def inventory_cover(tables, lines, start="1997-11-01", end=LAST_FULL_MONTH_END):
    """Estimate months of stock cover and a stock status per product.

    Args:
        tables (dict[str, pandas.DataFrame]): Output of
            ``load_tables``.
        lines (pandas.DataFrame): Output of ``build_order_lines``.
        start (str | pandas.Timestamp): First order date of the
            sales-rate window.
        end (pandas.Timestamp): Last order date of the window; its month
            is counted as a full month.

    Returns:
        tuple[pandas.DataFrame, int]: One row per product with
        ``UnitsPerMonth``, ``RecentRevenue``, months of cover on hand
        and including units on order (inf with no recent sales) and
        ``Status``; and the number of months in the window.
    """
    start = pd.Timestamp(start)
    months = (end.to_period("M") - start.to_period("M")).n + 1
    recent = lines[(lines["OrderDate"] >= start) & (lines["OrderDate"] <= end)]
    velocity = recent.groupby("ProductID")["Quantity"].sum() / months
    recent_revenue = recent.groupby("ProductID")["Revenue"].sum()

    products = tables["Products"][
        [
            "ProductID",
            "ProductName",
            "UnitsInStock",
            "UnitsOnOrder",
            "ReorderLevel",
            "Discontinued",
        ]
    ].copy()
    products["UnitsPerMonth"] = products["ProductID"].map(velocity).fillna(0.0)
    products["RecentRevenue"] = products["ProductID"].map(recent_revenue).fillna(0.0)
    products["MonthsCoverOnHand"] = products["UnitsInStock"] / products["UnitsPerMonth"]
    products["MonthsCoverInclOnOrder"] = (
        products["UnitsInStock"] + products["UnitsOnOrder"]
    ) / products["UnitsPerMonth"]

    def status(row):
        """Classify one product's stock position.

        Args:
            row (pandas.Series): Product row with ``Discontinued``
                and the two months-of-cover columns.

        Returns:
            str: "Discontinued", the stockout-risk label, the overstock
            label, or "Healthy".
        """
        if row["Discontinued"]:
            return "Discontinued"
        if row["MonthsCoverInclOnOrder"] < 1:
            return "Stockout risk (<1 month incl. on order)"
        if row["MonthsCoverOnHand"] > 3:
            return "Overstocked (>3 months on hand)"
        return "Healthy"

    products["Status"] = products.apply(status, axis=1)
    return products, months
