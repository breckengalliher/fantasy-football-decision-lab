# Start / Sit Lab

A live fantasy-football evidence app for comparing weekly lineup options.
It updates current-season player results and schedules from nflverse, then combines
recent production, season production, and opponent performance against the position
into a transparent PPR projection.

## What the app answers

> How do my players compare this week, and what evidence should inform my choice?

The decision room compares up to three players at the same position and shows:

- season PPR points per game;
- YTD box-score production and recent workload;
- average PPR output over the last four appearances;
- recent-form change versus the season baseline;
- the upcoming opponent's PPR allowed to the position;
- an explainable projected outcome and confidence label.
- neutral written outlooks for every selected player.

The system issues a Start or Sit verdict using only the documented core model.
Injuries, participation, weather, game environment, betting totals, personnel
changes, schedule-adjusted opponent strength, and uncertainty ranges are shown
as independent Decision Context and do not change that verdict.

Only verified nflverse player IDs with an upcoming game, at least two appearances,
and position-specific recent workload are included in the chooser. This prevents
demo names, inactive roster entries, and fringe players without meaningful usage
from crowding the comparison.

## Projection model

The current model deliberately favors clarity and stability:

```text
form estimate = 65% × last-four PPR/G + 35% × season PPR/G
projection = (90% season PPR/G + 10% last-four PPR/G) × conservative matchup adjustment
```

The weights were selected with a leakage-safe 2021–2023 backtest and checked on
the untouched 2024 season. The raw matchup index is capped between 0.85 and 1.15, and only 25% of that
adjustment reaches the projection. The effective matchup effect is therefore
limited to ±3.75%. A noisy defense ranking cannot overwhelm player production.

Confidence is based on player-game and opponent-position sample sizes. It does
not represent injury certainty.

## Live data

The app reads the current `player_stats` and `schedules` releases from
[nflverse](https://github.com/nflverse/nflverse-data) and caches them for one
hour. The UI includes a manual refresh action.

The core nflverse layer includes live snaps, pace, available game totals,
schedule-adjusted opponent context, and outcome ranges. Injuries, practice
status, pregame weather, and depth charts become available when SportsDataIO is
connected. Breaking news and week-over-week personnel-change detection remain
explicit limitations rather than being silently treated as neutral.

### Optional SportsDataIO context

The app includes an optional SportsDataIO adapter for current injuries, practice
status, pregame weather, game totals, and depth-chart context. Copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, then store your
private NFL API key there:

```toml
SPORTSDATAIO_API_KEY = "your-private-key"
```

You may alternatively define the `SPORTSDATAIO_API_KEY` environment variable.
Never commit the real key. Provider data is displayed as Decision Context and
is deliberately excluded from the Start/Sit model.

## Run locally

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

On Windows, `run_dashboard.ps1` launches the app after the dependencies are
installed.

## Project structure

```text
dashboard/app.py          # Streamlit decision experience
dashboard/data.py         # live loading and feature calculations
tests/test_live_dashboard.py
notebooks/                # retained research and model-validation history
src/                      # retained historical pipeline utilities
```

## Responsible use

This is a fantasy-football decision aid, not a guarantee or betting product.
Always check official player status and late news before kickoff.
