# Initial Data Audit

## Scope

- Source: nflverse modern-format weekly player statistics
- Seasons: 2021–2025
- Filter: regular season and listed position `WR`
- Unit of observation: one listed wide receiver in one NFL week

The intended time split is:

- **Development/training:** 2021–2023
- **Validation and rule selection:** 2024
- **Final unseen test:** 2025

The 2025 results must remain unopened until the feature, participation, and modeling rules are finalized using the earlier seasons.

## Audit results

| Check | Result | Interpretation |
|---|---:|---|
| All player-week rows | 94,845 | Includes all listed positions and postseason rows |
| Regular-season WR rows | 12,267 | Initial WR population |
| Unique WR player IDs | 457 | Stable IDs prevent name-based joins |
| Duplicate player-season-week keys | 0 | No duplicate keys found |
| Week range | 1–18 | Expected modern regular-season range |
| Missing targets | 0.00% | Complete in this population |
| Missing target share | 0.00% | Zero-target rows are explicitly recorded as zero |
| Missing receiving air yards | 0.00% | Complete in this population |
| Missing air-yard share | 0.00% | Zero-target rows are explicitly recorded as zero |
| Missing PPR points | 0.00% | Complete in this population |
| PPR formula mismatches | 0 | Source totals reconcile after including all scoring components |

## Season coverage

| Season | WR rows | Rows with targets | Zero-target rows |
|---:|---:|---:|---:|
| 2021 | 2,483 | 2,169 | 314 |
| 2022 | 2,387 | 2,096 | 291 |
| 2023 | 2,472 | 2,170 | 302 |
| 2024 | 2,427 | 2,087 | 340 |
| 2025 | 2,498 | 2,085 | 413 |

## Important findings

### Consistent source format

The 2025 release uses nflverse's newer player-stat format. Matching modern-format files were therefore downloaded for 2021–2024 instead of mixing 2025 with legacy files. This makes zero-opportunity appearances and columns consistent across seasons.

### Zero-target games

The modern files explicitly retain WR appearances with zero targets and record target share and air-yard share as zero. These games will remain in the rolling history because they contain meaningful evidence that the receiver played but received no passing opportunity.

### Negative air-yard share

There are 428 negative air-yard-share values. These arise from negative receiving air yards, such as targets behind the line of scrimmage, and should not automatically be treated as errors.

### Air-yard shares above 100%

Three values exceed 1.0. Because teammates can accumulate negative air yards, an individual receiver can account for more than the team's net air-yard total. These observations require review but are mathematically possible.

### Fantasy scoring reconciliation

The supplied PPR values match a full calculation incorporating passing, rushing, receiving, two-point conversions, special-teams touchdowns, and lost fumbles. This matters because some wide receivers record non-receiving statistics.

## Locked rolling-window decision

Rolling windows will use a receiver's previous **games played**, not the previous scheduled weeks.

Reason: scheduled-week windows would treat missed games as zero-performance observations and mix availability with the receiver's offensive role. Availability and injury effects can be modeled separately later.

For a prediction made before a player's next game, all rolling values will be shifted by one row so the current game's information cannot enter its own prediction.

## Decisions still required

1. Decide how early-season rows enter three- and five-game comparisons.
2. Review traded players and team changes before building team-relative features.
3. Confirm that identical eligible rows are used when comparing prediction windows.

## Recommended initial choices

- Retain zero-target appearances as games played. **Decision locked.**
- Require a complete five-game history for the primary head-to-head comparison.
- Use 2021–2023 for development, 2024 for validation, and 2025 for one final untouched test.
