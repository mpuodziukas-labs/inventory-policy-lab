# Inventory Policy Lab

Proves: reorder point, safety stock and order quantity can be derived from real weekly demand with formulas tested against textbook cases, and checked by a seeded simulation. Verify in 60s: `make test`.

A buyer for 40 fast-moving retail SKUs has to decide how much to order, when to reorder and how much safety stock to hold, without carrying more cash in stock than the service target requires. This lab takes 52 weeks of real demand, forecasts it, derives the economic order quantity, reorder point and safety stock for a 95 percent cycle service target, then replays each policy against thousands of simulated weeks with variable lead time to see whether the target is actually met and which SKUs miss it and why.

## Run it in 60 seconds

```
make test       # unit tests, hand-worked formula cases, drift test (stdlib + pytest)
make selftest   # plants a wrong formula, exits 0 only if the simulation check catches it
make regen      # rebuilds report/index.html, docs/recommendation.md, results/*.csv and the block below
```

Open `report/index.html` for the static report and read `docs/recommendation.md` for the findings. The data is vendored in `data/`; to rebuild it from the source download see `data/SOURCE.md`.

## Results

<!-- RESULTS:START -->
Forecast backtest: one-step-ahead rolling origin, 26 weeks minimum training, 26 test weeks per SKU.

| Method | WAPE, all 40 SKUs |
|---|---|
| Naive (last week) | 63.4% |
| Moving average (4 weeks) | 51.7% |
| Simple exponential smoothing (alpha 0.3) | 49.7% |

Simple exponential smoothing beats the naive forecast on WAPE for 40 of 40 SKUs.

Policy check by simulation (5200 weeks per SKU, seed 20261117), target cycle service level 95%, tolerance 3 points:

| Measure | Value |
|---|---|
| Target cycle service level | 95.0% |
| Mean achieved cycle service level | 94.0% |
| Mean achieved fill rate | 99.2% |
| SKUs meeting target | 31 of 40 |

Service level sensitivity (all 40 SKUs, assumptions in `config.json`):

| Target service level | z | Safety stock (units) | Safety stock holding cost per year (GBP) | Total holding cost per year (GBP) |
|---|---|---|---|---|
| 90.0% | 1.282 | 25,504 | 9,267 | 24,688 |
| 95.0% | 1.645 | 32,734 | 11,894 | 27,316 |
| 97.5% | 1.960 | 39,005 | 14,173 | 29,594 |
| 99.0% | 2.326 | 46,296 | 16,822 | 32,244 |
<!-- RESULTS:END -->

## Honesty Statement

- Demand is real: the UCI Online Retail dataset (Chen, D. (2015), https://doi.org/10.24432/C5BW33, CC BY 4.0), aggregated to ISO weeks for the 40 SKUs with the most weeks of sales.
- The source has no lead times, ordering costs or holding costs. Lead time (1, 2 or 3 weeks, mean 2, standard deviation 0.5), ordering cost per order (50) and annual holding rate (25 percent of median selling price) are stated assumptions in `config.json`. Change them and `make regen` recomputes everything. The policy numbers show how the method behaves under those assumptions, not what this retailer actually pays.
- The formulas follow published sources listed in `SPEC.md` with the line relied on. Where this lab substitutes something (WAPE for MAPE because weekly demand has zeros) `SPEC.md` says so.
- Every number in the block above is produced by `make regen` and checked by a test.

## Limitations

- Simulated demand is an independent resampling of each SKU's own 52 weeks, so trend, seasonality and week-to-week correlation are not represented.
- The safety stock formula assumes normal demand and independence of demand and lead time. SKUs with strongly skewed demand fall short of target, which the recommendation lists.
- One year of data is short for seasonal lines; the backtest has 26 test weeks per SKU.
- There is no supplier data, so supplier performance, procurement terms and logistics cost are not analysed. Only holding and ordering cost assumptions are modelled; there is no wider financial model.
- Price stands in for unit cost, and lost sales are assumed on a shortage (no backorders).
- The analysis is a worked example on one public dataset, not a connection to any ERP or planning system.
