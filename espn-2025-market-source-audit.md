# ESPN 2025 Cheat Sheet Source Audit

## Decision

Retain the supplied ESPN PDF as a historical market reference. Do not use it as
the 2026 dashboard's current market-price source.

## Source profile

- Title: ESPN 2025 Fantasy Football Draft Kit - PPR League Cheat Sheet
- Companion reviewed: ESPN 2025 PPR Top 300 Cheat Sheet
- Last updated: September 2, 2025
- Extracted player rows: 265
- Overall-rank range: 1–319
- Duplicate overall ranks: 0
- Salary-cap value range: $0–$57
- Extracted salary-cap dollars: $2,010

The normalized extract contains quarterbacks, running backs, wide receivers,
tight ends, and kickers. The D/ST rows use a different visual format and were
not included in the player extract.

The Top 300 PDF presents the same September 2, 2025 salary-cap values in overall
rank order and confirms the same 10-team roster and scoring assumptions. It
does not change the compatibility decision.

## Compatibility findings

The sheet assumes:

- 2025 season
- 10 teams
- $200 per team
- Four points per passing touchdown
- 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 D/ST
- Seven bench spots

The portfolio league uses 12 teams, six-point passing touchdowns, two FLEX
spots, no kicker, and six bench spots. The dollar values are therefore not
directly comparable.

## Risk and remediation

Using the file as current market data would create a high-severity season and
league-settings mismatch. The dashboard market importer now requires a `season`
column and rejects any file that is not exclusively 2026.

The extracted file remains useful for historical methodology examples and for
demonstrating source validation in the GitHub portfolio.
