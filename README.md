# Fantasy Football Decision Lab

An end-to-end data science portfolio project for identifying 2026 fantasy-football
draft targets and weekly start/sit options using advanced opportunity,
efficiency, projection, and matchup analysis.

## Project questions

> Which players offer the strongest value in a 12-team, full-PPR, $200 auction?

> Which available players provide the best weekly start/sit combination of
projected production, floor, ceiling, matchup, and confidence?

## Why this project matters

Fantasy managers often react to last week's points. This project tests whether repeatable indicators—such as targets, target share, air yards, and expected opportunity—provide better forward-looking signals.

## Deliverables

- Reproducible data preparation pipeline
- Position-specific exploratory and modeling notebooks
- SQL analysis of weekly receiver performance
- Time-aware fantasy-point projection models
- Breakout and regression-candidate analysis
- Draft Target Finder with league-calibrated auction values
- Weekly Start/Sit Analyzer
- Advanced Player Explorer
- Interactive Streamlit dashboard
- Plain-English findings and model limitations

## Default league

The portfolio default is a 12-team, full-PPR auction league with a $200 budget,
six-point passing touchdowns, 1 QB, 2 RB, 2 WR, 1 TE, 2 FLEX starters, 1 team
defense, and 6 bench slots. Kickers are excluded. See
[`auction-methodology.md`](auction-methodology.md).

The planned 2026 roster, schedule, rankings, ADP, and auction-market sources are
documented in [`data-source-plan.md`](data-source-plan.md).

## Dashboard preview

The Streamlit application is available in [`dashboard/app.py`](dashboard/app.py).
It opens to a summary-first Overview and includes the Draft Target Finder,
Weekly Start/Sit Analyzer, Player Explorer, and Methodology workspace. Its
current 2026 estimates use 2023–2025 nflverse results weighted toward 2025.
Its custom auction values are calculated from the configured league scoring,
180-player roster demand, positional replacement levels, and the complete
$2,400 league budget. External prices are optional comparisons only.

Build or refresh the draft board, then run locally:

```bash
python src/pipeline.py
streamlit run dashboard/app.py
```

On Windows, `run_dashboard.ps1` provides a convenient launcher after Python and
the requirements are installed.

The sidebar also accepts a reviewed auction-value CSV. Start from
`data/external/market_values_template.csv`; the required columns are `player`
`market_value`, and `season`. Only 2026 files are accepted. Values are matched
by normalized exact player name, and unmatched model rows keep the internal
last-season baseline.

The default comparison uses ESPN's August 9, 2026 PPR Top 300. ESPN publishes
10-team, $200 values, so the pipeline converts them to the portfolio's exact
12-team, 180-player, $2,400 auction pool: kickers are excluded, every drafted
player receives the $1 minimum, and the remaining dollars are allocated in
proportion to ESPN's published prices. The independent six-point passing-TD
model remains the primary recommendation. See
[`espn-2026-market-source-audit.md`](espn-2026-market-source-audit.md).

The prior RealTime Fantasy Sports benchmark and 2025 ESPN sheet remain retained
as dated reference sources, but neither is loaded by default.

## Initial metrics

| Category | Metric | Question it answers |
|---|---|---|
| Outcome | PPR fantasy points | How many fantasy points did the player score? |
| Opportunity | Targets | How often was the player given a receiving opportunity? |
| Opportunity | Target share | What percentage of team targets went to the player? |
| Opportunity | Air-yard share | What percentage of team air yards went to the player? |
| Role | Average depth of target | How far downfield was the player targeted? |
| Efficiency | Catch rate | How often did a target become a reception? |
| Efficiency | Yards per target | How many receiving yards resulted from each target? |
| Value | Fantasy points per target | How much fantasy production came from each target? |
| Stability | Rolling averages | Is the player's recent role consistent or volatile? |

See [`docs-metrics.md`](docs-metrics.md) for formulas, interpretations, and cautions.

## PPR scoring

The first version uses full PPR scoring:

```text
PPR points = receptions + 0.1 × receiving yards + 6 × receiving touchdowns
```

The pipeline also applies rushing, passing, two-point conversion, and turnover
scoring from `config/league.json`.

## Repository structure

```text
fantasy-football-wr-analytics/
├── data/                 # Raw and processed data (large files ignored)
├── notebooks/            # Reader-facing analyses
├── reports/figures/      # Exported charts for the README
├── sql/                  # Portfolio SQL queries
├── src/                  # Reusable Python functions
├── tests/                # Automated correctness checks
├── docs-metrics.md       # Beginner-friendly metric dictionary
└── roadmap.md            # Milestones and learning goals
```

## Data source

The primary source is the open-source [nflverse](https://nflverse.nflverse.com/)
ecosystem. The application records its model basis and separates historical
facts from 2026 estimates.

## Current status

**Milestone 1 complete:** project scope, PPR scoring, initial metric definitions, repository structure, and starter tests.

**Milestone 2 in progress:** 2021–2025 modern-format weekly data acquired and the initial quality audit completed. See [`data-audit.md`](data-audit.md) and the preregistered [`hypothesis.md`](hypothesis.md).

**Exploration and validation complete:** the first analysis notebook found that
five-game averages had the strongest correlations. The 2024 validation notebook
found that target share and air-yard share were not meaningfully better together
than target share alone, while combining opportunity metrics with recent PPR
produced the lowest validation error.

**Final holdout complete:** the locked combined model was evaluated once on
2025. It did not beat the simple five-game PPR baseline on primary MAE, although
it produced better RMSE and R² by reducing larger misses.

**Application pipeline connected:** the reproducible pipeline now joins the
Jul. 23, 2026 nflverse roster and schedule releases to historical player results,
applies the custom league scoring, estimates production from weighted 2023–2025
results, populates Week 1 opponents, and assigns replacement-level auction
values. Players without qualifying history remain explicit $1 placeholders.
The D/ST model uses 2023–2025 nflverse weekly team statistics and the configured
ESPN-style scoring rules.

The current nflverse/ESPN 2026 offensive depth chart is joined by GSIS player
ID. nflverse confirms that its injury source ended after 2024, with no current
replacement ETA. The dashboard therefore marks injury data unavailable and
keeps health out of its confidence and risk scores rather than treating missing
records as healthy. See
[`injury-source-assessment.md`](injury-source-assessment.md).

**Next:** connect current injuries, consensus projections, and ADP, then complete
deployment polish.

The experiment and early-season fallback rules are documented in [`methodology.md`](methodology.md).

## Skills demonstrated

Python · pandas · SQL · exploratory data analysis · feature engineering · statistics · machine learning · data visualization · Streamlit · Git/GitHub

## Responsible interpretation

This is an educational portfolio project, not betting advice. Prediction quality can be affected by injuries, weather, coaching changes, defensive matchups, small samples, and changes in source coverage.
