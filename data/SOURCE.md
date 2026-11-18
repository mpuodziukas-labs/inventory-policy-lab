# Data source

UCI Online Retail, Chen, D. (2015), https://doi.org/10.24432/C5BW33, licence CC BY 4.0
(see LICENSE-dataset.txt). 541,909 transaction rows, 2010-12-01 to 2011-12-09.

Download: `python3 scripts/fetch_data.py` fetches
https://archive.ics.uci.edu/static/public/352/online+retail.zip and checks its
SHA-256 against `f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b`.
Unzip, then `python3 scripts/make_extract.py "Online Retail.xlsx"` (needs openpyxl)
rewrites the two CSVs below.

| File | SHA-256 | Content |
|------|---------|---------|
| weekly_demand.csv | 26fb6a013c7794e7fc94e5173b3e036d7e69cd6e041fb198305d401e166b4969 | iso_week, stock_code, units for 40 SKUs over 52 ISO weeks (2010-W49 to 2011-W48) |
| sku_price.csv | d66e604979227b37bc49b053bd5c62c0b9589e9f736d6b1353d6ee15046f92d8 | median unit price (GBP) and most common description per SKU |

Extract rules:

- Partial first and last ISO weeks are dropped.
- Product codes are five digits plus up to two letters; POST, DOT, M, BANK CHARGES and other service codes are excluded.
- Rows with unit price of zero or less are excluded. Negative quantities count only on cancellation invoices (invoice number starts with C) and are netted against sales in the same week; weekly units are floored at zero.
- The 40 SKUs are those with the most weeks of non-zero demand, ties broken by total units then code.
