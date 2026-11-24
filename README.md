# Northwind Traders: Five Questions for Management

15.561 HW 3, AI-assisted business data analysis of the Northwind database.

**Webpage:** [https://meganshi-418.github.io/northwind-hw3-analysis/](https://meganshi-418.github.io/northwind-hw3-analysis/) (served from `docs/index.html`)

## Questions answered

1. Where is growth coming from, and which markets are losing ground?
2. How dependent are we on a few customers, and are any key accounts slipping away?
3. Do deeper discounts actually win bigger orders?
4. Why do orders arrive late, and is the shipper to blame?
5. Which products are about to run out, and where is cash tied up in slow stock?

## Reproduce everything

Requires Python 3.11 or later (tested with 3.13).

```bash
git clone https://github.com/meganshi-418/northwind-hw3-analysis.git
cd northwind-hw3-analysis
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python build_site.py
```

`build_site.py` reads `data/Northwind Database.xlsx` and regenerates:

| Output | What it contains |
|---|---|
| `docs/index.html` | The webpage. Every number and chart on it is generated, none typed by hand |
| `outputs/summary.json` | Headline figures, printed to the terminal as well |
| `outputs/q1_*.csv` | Monthly revenue; revenue by country for Jan–Apr 1997 vs 1998 |
| `outputs/q2_*.csv` | Customer revenue ranking with cumulative share; lapsed customers |
| `outputs/q3_discount_levels.csv` | Relative order size and revenue given away at each discount level |
| `outputs/q4_*.csv` | Late-shipment rates with 95% Wilson intervals, by delivery window and by shipper |
| `outputs/q5_inventory_cover.csv` | Sales rate, months of cover and stock status for every product |

To view the page locally, open `docs/index.html` in a browser. The charts load plotly.js from a CDN, so you need an internet connection.

Options: `python build_site.py --data path/to/workbook.xlsx --out outputs --site docs`.

### Check that it worked

`outputs/summary.json` should show `"total_revenue": 1265793.04`. This is the standard published Northwind
revenue total, so it confirms that revenue and the table joins are correct.

## Code layout

```
build_site.py                 entry point: runs the analysis and writes the outputs and webpage
northwind_analysis/data.py    loads the workbook, joins tables, calculates revenue and shipping fields
northwind_analysis/analysis.py  one function per analysis (growth, concentration, discounts, lateness, inventory)
northwind_analysis/figures.py   Plotly charts
templates/index.html          page text with $placeholders that build_site.py fills in
data/Northwind Database.xlsx  the course-provided dataset
```

Every function has a Google-style docstring, written with the course `python-docstrings` skill (SKILL.md).

## Definitions and analysis choices

- **Revenue** = `UnitPrice × Quantity × (1 − Discount)`. Uses the price recorded on each order line, not the Product sheet's list price.
- **Time window:** orders run from 1996-07-04 to 1998-05-06. May 1998 is partial, so trends stop at April 1998 and growth compares Jan–Apr 1998 with Jan–Apr 1997.
- **Lapsed customer:** at least 3 orders, and days since the last order (as of 1998-05-06) greater than twice the customer's average gap between orders.
- **Relative quantity:** an order line's quantity divided by the average undiscounted quantity for the same product. The 8 lines with non-standard 1–6% discounts are excluded.
- **Late:** `ShippedDate > RequiredDate`. The 21 orders not yet shipped are excluded.
- **Months of cover:** (UnitsInStock + UnitsOnOrder) ÷ average monthly units sold, Nov 1997 – Apr 1998. The stock figures are an undated snapshot and are treated as the position at the end of the order data.
- The extra columns in the Product sheet (`Cheap`, `NewPrice`, `IsCheap`, `Cheap.1`, `NewPrice.1`, `Unnamed: 14`) come from an earlier exercise and are not used.
