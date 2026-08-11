# D/ST Projection Methodology

## Purpose

Estimate 2026 team-defense fantasy scoring under the portfolio league's
ESPN-style rules, without a yards-allowed component.

## Historical inputs

The model uses nflverse weekly team statistics from the 2023, 2024, and 2025
regular seasons. Recent seasons receive more weight:

- 2023: 15%
- 2024: 30%
- 2025: 55%

## Weekly scoring

Each historical team-week receives:

- 1 point per sack
- 2 points per interception
- 2 points per opponent fumble recovery
- 2 points per blocked punt, PAT, or field goal
- 2 points per safety
- 6 points per defensive or special-teams touchdown
- Configured ESPN-style points-allowed tier points
- No yards-allowed points

Opponent defensive and special-teams touchdowns are removed from the raw
score before assigning the points-allowed tier. This is an approximation:
extra-point and two-point-conversion attribution can vary by fantasy platform.

## Projection and auction values

The weighted historical points-per-game estimate is multiplied by 17 games.
Because only 12 defenses are expected to be drafted, auction prices are kept
deliberately conservative:

- D/ST 1: $5
- D/ST 2–3: $4
- D/ST 4–6: $3
- D/ST 7–12: $2
- All others: $1

These are portfolio model values, not observed ESPN auction prices.

