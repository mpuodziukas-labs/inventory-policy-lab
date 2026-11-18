# Changelog

- spec: problem, exits, trace table, pipeline, standards
- test: hand-worked formula, forecast, simulation and trace tests
- feat: vendored weekly demand extract and fetch script
- feat: formulas, forecast, simulation, root cause, selftest
- feat: report, recommendation, README results block, CI
- docs: changelog
- test: receipts for selftest and regen
- test: trace, report and README drift tests; trace table recounted
- test: edge tests for simulation, extract, report and regen; spec row statuses
- test: pin service range, negative buffer, no-cycle, min order, selftest control, description
- fix: WAPE, MAE and zero-length window raise clear errors; pipeline names the SKU
- fix: constant-demand skewness is 0 by convention; decompose rejects zero variance
- fix: reject negative windows, actuals and decompose inputs, mae length mismatch; pin skewness and error chain
- fix: pin wape check order, reject length mismatch and non-finite inputs
- test: pin length-before-finite order in wape and mae, meets_target boundary
- test: pin draw fallback, short-history average, lead-time weights, tie and marker handling; drop unused next-week forecast
