# 2026 Dashboard Data-Source Plan

## Source principles

- Prefer reproducible public datasets with stable player IDs.
- Preserve retrieval dates and source URLs.
- Do not commit large raw files to GitHub.
- Do not redistribute proprietary rankings or projections without confirming
  permission; store retrieval code and derived outputs when permitted.
- Label preseason estimates separately from observed regular-season statistics.

## Planned sources

### nflverse

Primary source for:

- historical and current player statistics
- 2026 rosters
- schedules and opponents
- player identity mappings
- depth charts, injuries, participation, and snap information when available
- expected fantasy opportunity

Reference:

- https://nflreadr.nflverse.com/reference/index.html
- https://nflreadr.nflverse.com/reference/load_player_stats.html
- https://nflreadr.nflverse.com/reference/load_rosters.html
- https://nflreadr.nflverse.com/reference/load_schedules.html

### FantasyPros expert consensus rankings through nflverse

The nflverse `load_ff_rankings()` interface accesses the DynastyProcess archive
of FantasyPros expert consensus rankings and supports preseason, weekly, and
historical ranking modes.

Reference:

- https://nflreadr.nflverse.com/reference/load_ff_rankings.html

Planned uses:

- preseason ranking benchmark
- weekly start/sit benchmark
- ranking uncertainty using expert dispersion
- model-versus-market comparisons

### 2026 PPR ADP

FantasyPros currently publishes a 2026 PPR ADP consensus across multiple draft
platforms.

Reference:

- https://www.fantasypros.com/nfl/adp/ppr-overall.php

Planned uses:

- market draft order
- positional market rank
- value-gap analysis

### Auction-price benchmark

The dashboard's primary dollar values will be calculated from the configured
league's projections and value-over-replacement method. External auction values
will be treated as market context rather than ground truth.

Potential references:

- ESPN 2026 PPR draft kit salary-cap values
- FantasyPros salary-cap values
- other publicly downloadable $200 PPR auction tables with clear attribution

Because the league has two FLEX positions, six-point passing touchdowns, no
kicker, six bench slots, and no yards-allowed defense scoring, external values
must be recalibrated before comparison.

## Refresh cadence

### Preseason

- rosters and depth charts: daily or on demand
- injuries and news-derived availability: daily
- ADP and expert rankings: at least weekly
- projections and auction values: after every material source refresh

### Regular season

- player statistics: after each game day
- injuries, depth charts, and availability: daily
- weekly rankings and matchups: daily, with a final game-day refresh
- start/sit projections: after every material update

## Provenance fields

Every dashboard dataset should include:

- `source_name`
- `source_url`
- `retrieved_at`
- `season`
- `week` where applicable
- `source_player_id`
- `canonical_player_id`
- `scoring_profile`
- `model_version`
- `data_status` such as preseason, observed, projected, or stale
