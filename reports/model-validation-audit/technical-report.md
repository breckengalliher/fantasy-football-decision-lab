# The Sunday Decision Lab Projection Model: Baseline Validation and Research Plan

## Technical summary

The approved round-three model remains the production incumbent. On 3,170 eligible player-weeks in the untouched 2025 walk-forward test, it produced **5.526 PPR MAE**, **7.182 RMSE**, **−0.187 PPR mean bias** (actual minus projection), and **68.30% cross-position weekly ordering accuracy**. Its empirical production P10–P90 band covered **79.65%** of 2025 outcomes with a mean width of **16.77 PPR**, closely matching the nominal 80% target.

A regularized opportunity-plus-efficiency challenger improved 2025 MAE to **5.478** and ordering accuracy to **68.42%**. The MAE difference was **−0.048 PPR**, with a week-clustered 95% interval of **−0.093 to −0.004**. This is positive research evidence, but the 0.87% relative MAE improvement is below the proposed 1% promotion threshold and has not passed prospective shadow testing. **Recommendation: retain the incumbent, run the challenger in shadow mode, and collect at least four weeks of immutable pre-kickoff forecasts before reconsidering promotion.**

The strongest verified weaknesses are not solved by presenting more decimal precision. Comparisons separated by less than two projected points were ordered correctly only **54.09%** of the time. QB forecasts had the highest position MAE (**6.654**, n=471), and high-workload players had the highest workload-tier MAE (**6.556**, n=1,029). Those findings support better opportunity and role forecasting, a dedicated QB validation track, and calibrated communication of close decisions.

## What the evidence says

### The incumbent beats every simple historical-average baseline

All benchmarks used the same 2025 evaluation player-weeks and pre-week box-score information. The incumbent beat season-to-date average, three-game average, five-game average, exponentially weighted average, and an opportunity-only estimate on MAE and weekly ordering. This supports keeping the current blend of production, workload, prior history, touchdown regression, and bounded matchup context as the production baseline.

| Model | MAE | RMSE | Bias | Ordering accuracy |
|---|---:|---:|---:|---:|
| Regularized opportunity + efficiency | 5.478 | 7.165 | +0.058 | 68.42% |
| Approved round-three incumbent | 5.526 | 7.182 | −0.187 | 68.30% |
| Season-to-date average | 5.630 | 7.418 | −0.062 | 67.42% |
| Five-game rolling average | 5.714 | 7.518 | −0.252 | 67.24% |
| Exponentially weighted average | 5.722 | 7.553 | −0.241 | 67.18% |
| Opportunity only | 5.774 | 7.466 | −0.355 | 66.58% |
| Three-game rolling average | 5.964 | 7.838 | −0.433 | 66.03% |

The regularized challenger used 2021–2023 for initial fitting, 2024 to select ridge penalty strength, and 2025 once as the final chronological test. Its small advantage should be treated as a candidate, not a production win.

### Close decisions are uncertainty problems, not strong recommendations

Incumbent ordering accuracy increased with projected separation: 54.09% below two PPR, 63.57% from two to five, 75.49% from five to ten, and 86.83% above ten. Raw pair counts are correlated and are not treated as independent observations; the overall week-clustered 95% ordering interval was 67.47%–69.36%.

Product implication: projections separated by less than two points should remain “close call” or “lean” decisions. A strong-edge label is not statistically defensible from this evidence alone.

### Error is concentrated among quarterbacks and high-volume players

The incumbent's 2025 MAE by position was QB 6.654 (n=471), RB 5.830 (n=825), WR 5.460 (n=1,193), and TE 4.494 (n=681). High-opportunity players had 6.556 MAE versus 4.299 in the low-opportunity tier. WR forecasts carried the largest position bias at −0.558 PPR, meaning the model modestly overprojected WR scoring on average.

These results do not prove which missing feature causes each error. They do establish where controlled experiments have the highest expected value: QB scoring and rushing-role modeling, high-volume role forecasting, and WR efficiency shrinkage.

## Verified production architecture

### Raw and provider inputs

- Weekly player statistics come from nflverse-compatible weekly files and include attempts, carries, targets, yardage, touchdowns, target share, and air-yards fields.
- The weekly publication pipeline enriches the board with SportsDataIO schedule, depth-chart, weather, betting, and availability context; separate injury, reporting, headshot, and player-market sources add supplementary context.
- The web app reads precomputed compact parquet boards for both four-point and six-point passing-touchdown settings. Expensive rebuilding happens in scheduled refresh jobs rather than normal user interactions.
- Live context and market fields are deliberately supplemental unless explicitly incorporated by the approved formula. Market-implied PPR does not currently overwrite the model ranking.

### RB, WR, and TE calculation

1. Current production is the season-to-date PPR average; recent workload is the last three games' carries plus targets.
2. Observed touchdown scoring receives 25% weight and 75% is replaced by the current position touchdown rate applied to recent opportunity.
3. The current signal is 75% touchdown-regressed production plus 25% workload-implied scoring.
4. The prior-season signal receives the same touchdown-regression treatment; when prior history is unavailable, workload is the fallback.
5. Current-season weights are 40% through two games, 60% through six, 75% through ten, and 90% afterward.
6. A verified role-change rule adds ten percentage points (capped at 90%) after at least five games when recent opportunity is at least 125% of the prior rate and recent opportunity share is at least 115% of the prior share.
7. The matchup index is opponent fantasy points allowed at the position divided by the position league average, raw-clipped to 0.90–1.10. The allowed adjustment starts with a ±3% cap in Week 5, grows by one point per week to ±10%, and is shrunk by opponent-position sample size divided by 24.

### QB calculation

The QB path recalculates fantasy points for both four- and six-point passing touchdowns, retains rushing scoring, regresses passing-touchdown and turnover rates toward league/prior expectations, blends current and history signals with the same sample-size schedule, and applies a bounded opponent factor. Inexperienced, mobile, and pocket archetypes select separate empirical range offsets. The historical audit in this report validates the four-point format only; the six-point live calculation exists but still needs a separately specified chronological audit.

### Ranges and recommendations

RB/WR/TE ranges use out-of-sample empirical residual offsets by position and sample-size bucket. QB ranges use separate scoring-format and archetype calibration. Start/sit ranking is the median point estimate; UI edge labels should reflect separation and calibrated uncertainty rather than fabricated confidence percentages.

## Historical data and leakage assessment

The local weekly archive contains 29,340 regular-season QB/RB/WR/TE player-weeks from 2021–2025, with no duplicate player-week keys and no missing player, week, position, opponent, or PPR outcome fields. Box-score opportunity (attempts, carries, targets) and basic receiving-efficiency fields are available.

This archive does **not** contain complete point-in-time routes, route participation, first-read share, offensive snaps, timestamped injury history, or timestamped market states. The historical results are therefore legitimate walk-forward box-score simulations—not an archive of exact projections previously shown to users. Final injury reports, late depth changes, and other retrospectively available context must not be attached to those historical rows and described as pregame evidence.

The new prospective projection ledger closes the most important governance gap. Every scheduled publication now creates separate append-only forecast files for four- and six-point formats containing forecast timestamp, information cutoff, season/week, player/game context, model version, expected points, median, interval, input fingerprint, and availability scenario. Mutable `*_current` boards remain for the application; the ledger is never silently overwritten.

## Validation design and metric definitions

- **Population:** eligible QB/RB/WR/TE player-weeks retained by the historical model's minimum-history and workload rules.
- **Scoring:** full PPR with four-point passing touchdowns for the completed benchmark.
- **Chronology:** 2021–2023 initial training, 2024 model selection, 2025 final test.
- **MAE:** mean absolute difference between actual and projected PPR.
- **RMSE:** square root of mean squared error; it penalizes large misses more heavily.
- **Bias:** mean actual minus projection; negative values indicate average overprojection.
- **Ordering accuracy:** share of non-tied player pairs within the same NFL week ordered correctly. Gap buckets use absolute projected difference. Pair counts are descriptive; uncertainty is clustered at the NFL-week level.
- **P10–P90 coverage:** share of actual results between the published lower and upper residual-based bounds. Mean width measures sharpness.

The challenger is a transparent ridge regression using position plus pre-week games played, current scoring, touchdown scoring, recent opportunities/share, prior-season production/opportunity, position scoring rates, and the incumbent matchup index. Missing numeric history is imputed from training-period medians, numeric inputs are standardized, and the intercept is unpenalized.

## Limitations and robustness

- The final 2025 test has only 16 NFL-week clusters; the challenger MAE interval excludes zero narrowly and should not be generalized without prospective evidence.
- The challenger improves MAE by 0.048 PPR (0.87%), below the proposed 1% materiality threshold.
- Raw pairwise observations are highly correlated because each player appears in many comparisons. Week-clustered intervals are the decision evidence; raw pair counts are included only for transparency.
- The current matchup feature uses opponent fantasy points allowed from earlier current-season games. It is sample-shrunk and capped, but it is not yet a full opponent/offense schedule-strength model.
- Historical validation does not reproduce exact late injury, depth-chart, weather, or market states. Those sources remain prospective or informational until their timestamped archives are sufficient.
- The report validates the current P10–P90 production interval, not a replacement P20–P80 range. No live range formula was changed.

## Five highest-value controlled experiments

1. **Opportunity-first versus regularized opportunity-plus-efficiency shadow models.** The current challenger is the only tested model to beat the incumbent on both 2025 MAE and ordering. Add routes, snaps, and first-read share only after trustworthy point-in-time collection begins. Complexity: medium; inference cost: negligible once precomputed.
2. **Dedicated QB four-/six-point validation.** QB error is highest. Build separate chronological scoring-format datasets and test dropbacks, designed rushes, scrambles, red-zone attempts, and archetype shrinkage. Complexity: medium; expected production cost: low.
3. **Verified role-change state model.** Compare the current threshold rule with exponential-decay workload and a regularized change-point state. Require multiple supporting signals and test false-positive role expansions. Complexity: medium.
4. **Schedule-adjusted opponent strength.** Replace raw opponent points allowed with a ridge/partial-pooling residual that controls for offenses faced and sample size. Evaluate by position and week. Complexity: medium; scheduled compute only.
5. **Conditional distribution calibration.** Fit experimental P20/P80 quantiles by position, workload, and sample history; evaluate coverage, interval score, and drift. Keep the current P10/P90 production ranges until a challenger passes validation. Complexity: medium.

Injury redistribution, weather, and defensive-personnel experiments remain later priorities because trustworthy historical timestamps are the binding constraint, not model sophistication.

## Computational architecture

Render Starter remains sufficient for serving precomputed projections to the current user base. Training and historical backtests should run in GitHub Actions or a research workstation, never during Streamlit interactions. The production service should load only the selected compact weekly board, cache shared immutable data, and perform lightweight selection and presentation.

The ledger adds storage and Git history but no normal interaction-time compute. Long-term, compact ledgers can be partitioned by season/week and archived after the season. The UI should not load the historical ledger unless an internal accuracy page explicitly requests aggregated results.

## Promotion gates defined before the next test

A challenger should be recommended only if it satisfies all of the following without changing the holdout definition after seeing results:

- At least 1% relative MAE improvement and a week-clustered 95% MAE-difference interval whose upper bound is at or below zero.
- RMSE degradation no worse than 1%, absolute bias no worse than 0.25 PPR, and extreme-miss rate no materially worse.
- No position with adequate sample size degrades by more than 2% MAE.
- Overall ordering improves by at least 0.5 percentage points, or is non-inferior within 0.25 points while point accuracy improves materially.
- Close-decision accuracy does not degrade by more than 0.5 percentage points.
- Interval coverage is within ±3 percentage points of its nominal target with equal or better proper interval score.
- Evidence repeats in at least two chronological evaluation periods and at least four prospective NFL weeks.
- Weekly inference remains precomputable and does not materially increase Render memory, latency, provider dependence, or failure risk.

The current regularized challenger does not yet clear the 1% improvement or prospective-shadow gates.

## Recommended next steps

1. Begin writing every weekly publication to the new immutable ledger and reconcile actual outcomes after games finalize.
2. Run the regularized challenger as a non-production shadow model for at least four weeks, preserving every version before kickoff.
3. Add a dedicated six-point QB historical evaluation before making any scoring-format claims.
4. Start point-in-time collection for routes, snaps, first-read share, injury updates, and depth-chart changes; do not backfill those from postgame states.
5. Build the internal accuracy view from ledger aggregates, with metric definitions, sample size, model version, and period attached to every claim.

## Accepted operating policy and initial implementation

The following policy was approved after the baseline audit:

- The approved round-three model remains the production model.
- The regularized opportunity-plus-efficiency challenger runs only in an isolated shadow ledger for at least four NFL weeks.
- QB evaluation is separated into four-point and six-point passing-touchdown formats.
- Injury, practice, depth-chart, and snap context is archived with observation timestamps. Routes and first-read share remain explicitly unavailable from the current providers and are not inferred.
- Projected gaps below two PPR are always communicated as close calls rather than strong edges.

The initial QB-format reconstruction is encouraging but remains non-production research. On 467 eligible 2025 QB-weeks, the approved-formula reconstruction produced 6.741 MAE and 59.31% ordering accuracy in the four-point format, beating season average at 6.908 MAE and 58.80% ordering. In the six-point format it produced 8.382 MAE and 58.60% ordering, also beating season average at 8.634 MAE and 58.06%. Because the local archive lacks exact historical starter designations and other late context used by the live gate, prospective confirmation is still required before any formula change.

## Decisions requiring approval

- Promotion of any challenger to the live projection formula.
- Purchase or adoption of a paid point-in-time routes, injury, or market data provider.
- Publication of an external-facing model-accuracy page.
- Any change from the current P10–P90 production ranges to P20–P80 or another interval.
- Any hosting upgrade or migration. None is recommended from this audit.

## Further questions

- Can an affordable source provide historically timestamped routes, snaps, first-read share, and official injury changes under terms suitable for model validation?
- What minimum prospective ledger sample should be required by position before public accuracy claims are permitted?
- Should the product optimize a single ordering policy across flex positions, or maintain separately calibrated decision thresholds for QB and FLEX comparisons?

---

Supporting artifacts: `model-validation-audit.json`, `benchmark-summary-2025.csv`, `benchmark-predictions-2025.parquet`, `src/model_validation_audit.py`, and `src/projection_ledger.py`.
