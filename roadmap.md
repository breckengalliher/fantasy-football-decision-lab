# Project Roadmap

## Milestone 1 — Foundation

- [x] Define the portfolio question
- [x] Select wide receivers as the initial position
- [x] Document PPR scoring
- [x] Create an initial metric dictionary
- [x] Add tested scoring functions

**What you should be able to explain:** the difference between an outcome, an opportunity metric, and an efficiency metric.

## Milestone 2 — Data audit

- [x] Download several seasons of weekly nflverse player data
- [x] Filter to regular-season wide receivers
- [x] Inspect rows, columns, missing values, duplicates, and season coverage
- [x] Confirm the available target-share and air-yard-share fields
- [x] Create an initial data-audit report
- [ ] Lock participation, missing-value, and rolling-window rules

**What you should be able to explain:** why data quality must be checked before analysis.

## Milestone 3 — Exploratory analysis

- [x] Compare targets and fantasy points
- [x] Compare air-yard share and future fantasy points
- [x] Compare one-, three-, and five-game rolling windows
- [x] Separate descriptive findings from predictive evidence

**What you should be able to explain:** correlation does not prove causation or prediction.

## Milestone 4 — SQL portfolio analysis

- [ ] Weekly leaders
- [ ] Rolling opportunity leaders
- [ ] High-volume, low-production receivers
- [ ] Potential regression candidates

**What you should be able to explain:** filtering, grouping, window functions, and ranking.

## Milestone 5 — Prediction

- [x] Create a five-game rolling PPR baseline
- [x] Train interpretable linear validation models
- [x] Compare 2024 MAE, RMSE, and R-squared
- [x] Lock the model that will advance to the untouched 2025 test
- [x] Run the final 2025 holdout test once
- [ ] Train a regularized linear model
- [ ] Train one tree-based model
- [ ] Evaluate future seasons only; never randomly mix weeks
- [ ] Compare MAE and RMSE with the baselines

**What you should be able to explain:** training data, test data, features, target, baseline, and leakage.

## Milestone 6 — Interpretation and dashboard

- [ ] Explain model drivers
- [ ] Identify breakout and regression candidates
- [ ] Build player trend pages
- [ ] Add a weekly ranking view
- [ ] Publish a clear limitations section

**What you should be able to explain:** what the model learned, where it fails, and how a fantasy manager could use it.

## Milestone 7 — GitHub and résumé polish

- [ ] Add final charts and findings to README
- [ ] Add environment and reproduction instructions
- [ ] Review every claim against executed output
- [ ] Write résumé bullets and interview talking points
- [ ] Publish the repository
