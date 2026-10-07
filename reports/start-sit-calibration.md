# Start/Sit calibration report

## Decision

The live core projection now uses **90% season PPR per game, 10% last-four PPR
per game, and 25% of the capped opponent adjustment**. No injury, participation,
weather, betting, personnel, pace, or schedule-adjusted context enters this formula.

## Validation design

- Training/tuning seasons: 2021–2023
- Untouched holdout season: 2024
- Eligible holdout rows use at least three prior appearances and the same
  position-specific opportunity floors as the app.
- Every prediction uses games before the predicted week only.

## Holdout results

| Model | MAE | RMSE | Correlation |
|---|---:|---:|---:|
| Calibrated core | 5.514 | 7.215 | 0.519 |
| Previous 65% recent / 35% season | 5.604 | 7.309 | 0.509 |
| Season-only, no matchup | 5.521 | 7.221 | 0.517 |

The improvement is modest but repeatable on unseen data: about **1.6% lower MAE**
than the previous formula. A clustered bootstrap puts the MAE improvement at
0.047–0.134 PPR points (95% interval), so the direction is unlikely to be sampling noise.

The isolated matchup benefit is much less certain: its holdout MAE improvement is
0.004 points, with a 95% interval from -0.009 worse to 0.016 better. It remains in
the product because matchup is part of the requested decision methodology, but is
strictly capped and must not be described as a proven large edge.

The calibrated model ordered two same-position players correctly **66.73%** of the
time on the 2024 holdout, versus **66.32%** for the previous formula. This measures
the app's actual comparison task more directly than error alone.

## Outcome ranges

The displayed floor and ceiling now use position-specific 20th and 80th percentile
forecast-error offsets learned from 2021–2023. They remain supplementary context
and do not change the Start/Sit ordering.

| Position | Floor offset | Ceiling offset | Training samples |
|---|---:|---:|---:|
| QB | -6.74 | +6.17 | 1,324 |
| RB | -5.69 | +5.65 | 2,510 |
| WR | -6.07 | +4.95 | 3,841 |
| TE | -4.15 | +4.31 | 1,857 |

MAE is still roughly 5.5 PPR points, so small projection differences should not be
presented as certainty. The app explicitly marks spreads below 2.5 points as close
calls while still honoring the requested Start/Sit labels.

## Robustness decisions

- Position-specific weights were tested but rejected: their holdout improvements
  were tiny and inconsistent, increasing overfitting risk.
- Betting, injuries, snaps/routes, weather, pace, personnel changes,
  schedule-adjusted opponent strength, and outcome ranges remain excluded from
  Start/Sit ordering.
- The 2024 holdout was not used to select the weights.
