# The Sunday Decision Lab

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
- narrative-only player reporting from ESPN's NFL feed and recent public Bluesky reporter posts, with source links and no effect on projections.

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

The core nflverse layer includes player results, schedules, snaps, pace,
schedule-adjusted opponent context, and daily injury/practice reports. Sleeper
provides a once-daily fallback designation when nflverse has no designation and
is also used to flag source disagreements. Pregame weather, available game
totals, and depth charts become available when SportsDataIO is connected.
Breaking news remains an explicit limitation rather than being silently treated
as neutral.

### Optional SportsDataIO context

The app includes an optional SportsDataIO adapter for pregame weather, game
totals, and depth-chart context. Copy
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

## Production refreshes

GitHub Actions owns the production schedule. `general-context-refresh.yml`
updates injuries, depth charts, weather, game context, reporting and roster
photos at 6:00 AM and 5:00 PM Central. `daily-injury-refresh.yml` performs
lightweight injury, availability, weather and depth-chart checks during
practice-report and game-day windows without recalculating projections.
`weekly-production-refresh.yml` performs the full post-week projection rebuild
and complete test suite every Tuesday at 6:00 AM America/Chicago. The workflows can be
run manually, serialize through one production-refresh concurrency group, retain
downloadable artifacts, and publish validated snapshots to the repository's
raw cloud endpoint. The app checks that endpoint every five minutes, so a
data-only update does not need to restart the Render service.
The SportsDataIO key is read only from the protected GitHub Actions repository
secret named `SPORTSDATAIO_API_KEY`. The public Streamlit process reads only
these committed snapshots and never calls an upstream provider on behalf of a
visitor.

The same cloud refresh collects a limited set of recent journalism and public
reporter posts for roster-relevant players. It stores short theme-based
summaries and source links inside the published snapshot. This reporting layer
is appended only after projections and verdicts are finalized; it cannot change
any projection, range, ranking, or Start/Sit label.

## Always-on hosting

Community Cloud remains the preview deployment. Continuous availability uses
the paid Render web service defined in `render.yaml`, built from the repository
`Dockerfile`. Render checks Streamlit's `/_stcore/health` endpoint and
is deployed when application code changes; data-only snapshot commits do not
restart the service.

The web container contains only the public application and committed snapshot
files. It does not receive `SPORTSDATAIO_API_KEY` and cannot call production
providers. GitHub Actions remains the only production snapshot writer.

### Protected manual refresh center

Visitors can use **Check for latest updates** to reload the newest validated
cloud snapshot without calling a provider. The optional admin refresh center
securely dispatches the existing GitHub Actions workflows from the hosted app.
Configure these protected Render environment variables:

- `ADMIN_REFRESH_PASSWORD`: the private password used to unlock admin controls.
- `GITHUB_ACTIONS_TOKEN`: a fine-grained GitHub token with Actions write access
  to `breckengalliher/fantasy-football-decision-lab`.
- `REFRESH_GITHUB_REPOSITORY`: optional repository override; defaults to the
  production repository above.

The password and token stay server-side. The controls reject overlapping jobs
and enforce a 15-minute cooldown. **Run everything** dispatches the full weekly
workflow, rebuilding both scoring formats, refreshing context, running the test
suite and publishing only validated snapshots.

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
