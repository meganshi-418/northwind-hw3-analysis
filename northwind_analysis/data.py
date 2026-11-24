"""Load the Northwind workbook and build analysis-ready tables."""

from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "Northwind Database.xlsx"

# Last full month of data. Orders run to 1998-05-06, so May 1998 is partial.
LAST_FULL_MONTH_END = pd.Timestamp("1998-04-30")
DATA_END = pd.Timestamp("1998-05-06")


def load_tables(path=DEFAULT_PATH):
    """Read every sheet of the Northwind workbook.

    Args:
        path (str | pathlib.Path): Northwind Excel workbook; defaults to
            ``data/Northwind Database.xlsx`` in the repository.

    Returns:
        dict[str, pandas.DataFrame]: One table per sheet, keyed by sheet
        name, with "Orders Details" renamed to "OrderDetails" and
        "Product" renamed to "Products".
    """
    tables = pd.read_excel(path, sheet_name=None)
    tables["OrderDetails"] = tables.pop("Orders Details")
    tables["Products"] = tables.pop("Product")
    return tables


def build_order_lines(tables):
    """Join order lines to orders, products, categories and customers.

    Adds ``GrossRevenue``, ``Revenue`` (after discount) and
    ``DiscountAmount`` columns, all in USD. ``tables`` is not modified.

    Args:
        tables (dict[str, pandas.DataFrame]): Output of
            ``load_tables``.

    Returns:
        pandas.DataFrame: One row per order line with order date,
        customer, country, product and category attached.

    Raises:
        ValueError: If a join changes the number of order lines.
    """
    details = tables["OrderDetails"].copy()
    details["GrossRevenue"] = details["UnitPrice"] * details["Quantity"]
    details["Revenue"] = details["GrossRevenue"] * (1 - details["Discount"])
    details["DiscountAmount"] = details["GrossRevenue"] - details["Revenue"]

    products = tables["Products"][["ProductID", "ProductName", "CategoryID"]]
    categories = tables["Categories"][["CategoryID", "CategoryName"]]
    customers = tables["Customers"][["CustomerID", "CompanyName", "Country"]]
    orders = tables["Orders"][
        ["OrderID", "CustomerID", "EmployeeID", "OrderDate", "ShipVia"]
    ]

    lines = (
        details.merge(orders, on="OrderID", how="left", validate="many_to_one")
        .merge(products, on="ProductID", how="left", validate="many_to_one")
        .merge(categories, on="CategoryID", how="left", validate="many_to_one")
        .merge(customers, on="CustomerID", how="left", validate="many_to_one")
    )
    if len(lines) != len(details):
        raise ValueError("Join changed the number of order lines.")
    return lines


def build_orders(tables):
    """Add shipper name and delivery timing columns to the orders.

    Args:
        tables (dict[str, pandas.DataFrame]): Output of
            ``load_tables``.

    Returns:
        pandas.DataFrame: One row per order with ``Shipper``,
        ``LeadDays`` (order to ship), ``WindowDays`` (order to required
        date) and ``Late`` (shipped after the required date; False for
        unshipped orders).
    """
    orders = tables["Orders"].copy()
    shippers = tables["Shippers"].rename(
        columns={"ShipperID": "ShipVia", "CompanyName": "Shipper"}
    )[["ShipVia", "Shipper"]]
    orders = orders.merge(shippers, on="ShipVia", how="left")
    orders["LeadDays"] = (orders["ShippedDate"] - orders["OrderDate"]).dt.days
    orders["WindowDays"] = (orders["RequiredDate"] - orders["OrderDate"]).dt.days
    orders["Late"] = orders["ShippedDate"] > orders["RequiredDate"]
    return orders
