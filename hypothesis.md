# Pre-Analysis Hypothesis

This hypothesis was written before examining model results.

## Primary hypothesis

A wide receiver's rolling target share and rolling air-yard share will predict following-week PPR points better than either current-week opportunity metrics or current-week fantasy points.

## Predicted best window

The five-game rolling window will produce the lowest following-week prediction error.

## Reasoning

Five games should provide enough observations to reduce the influence of unusually high or low performances while remaining recent enough to represent the player's continuing role within their offense.

## Competing windows

- Previous game: responsive but volatile
- Previous three games: captures rapid role changes but may remain noisy
- Previous five games: predicted balance of stability and recency
- Season to date: stable but potentially slow to recognize breakouts or role changes

## Evaluation rule

Each version will be evaluated on identical eligible player-weeks. Mean absolute error will be the primary metric: the model or baseline with the lowest error performs best. All predictors must be shifted so that the game being predicted is excluded. Rolling windows use previous games played rather than scheduled weeks.

Listed games with zero targets count as games played and contribute zero target share and zero air-yard share to the rolling averages. This preserves evidence that the receiver played without receiving passing-game opportunity.

The 2021–2023 seasons will be used for development, 2024 for validation, and 2025 for one final unseen test after all rules are locked.

## What would disprove the hypothesis?

The hypothesis will not be supported if another window or the current-week fantasy-point baseline produces lower following-week error on the unseen test season.

## Secondary hypothesis

A model combining five-game target share and five-game air-yard share is expected
to outperform a model using five-game target share alone. The reasoning is that
target share represents opportunity volume while air-yard share may add
information about the potential value and depth of those opportunities.

## Final test outcome

The untouched 2025 test did not support the primary MAE hypothesis:

- Five-game PPR baseline MAE: `4.607`
- Locked combined-model MAE: `4.623`

The combined model did improve the secondary RMSE metric (`6.172` versus
`6.368`), but MAE was selected as the primary metric before the holdout was
opened. The 2025 holdout is now spent.
