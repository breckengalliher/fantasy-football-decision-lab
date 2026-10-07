"""User-facing source attribution and responsible-use language."""

SOURCE_ATTRIBUTION = """
**Data sources**

- **Player results, schedules, snap counts, team play volume, game lines and schedule data:** [nflverse public data releases](https://github.com/nflverse/nflverse-data). nflverse republishes and standardizes NFL data; it is not affiliated with the NFL.
- **Injuries and practice participation:** [nflverse daily injury reports](https://github.com/nflverse/nflverse-data), with [Sleeper](https://docs.sleeper.com/) used only as a once-daily fallback or disagreement check. nflverse remains authoritative when both sources provide a designation.
- **Pregame weather, game totals and depth charts:** [SportsDataIO](https://sportsdata.io/), when the provider connection is available. The time shown in the app is when this app last retrieved the provider data—not a guarantee that every underlying report changed at that time.
- **Model calculations and Start/Sit labels:** produced by this app from the credited source data. They are not rankings or projections supplied by nflverse, SportsDataIO, the NFL, ESPN, or the listed teams.

Missing provider data is labeled unavailable or not connected; it is never silently interpreted as healthy, active, or unchanged.
"""

METHODOLOGY_LANGUAGE = """
**What determines the Start/Sit label**

The app ranks only the players selected in the same comparison. “Start” means the highest median projection among those choices; “Sit” means a lower-ranked choice in that comparison. It is not a universal command to start or bench that player.

- **RB, WR and TE:** current-season PPR production is adjusted toward repeatable recent workload. Touchdowns are regressed toward position-level opportunity rates, prior-season production fades as the current-season sample grows, and the opponent adjustment is capped and scaled to the amount of evidence available.
- **QB:** the selected 4-point or 6-point passing-touchdown setting is applied throughout. Recent passing/rushing workload, regressed touchdown and turnover rates, a fading prior-season anchor, and a capped opponent adjustment form the median estimate. Only quarterbacks verified as QB1 by the connected depth-chart feed can enter the public comparison pool.
- **Ranges:** Floor, projection and ceiling are calibrated P10, median and P90 outcomes. They describe model uncertainty, not minimums or maximums; roughly 10% of outcomes may fall below the floor and 10% above the ceiling if calibration continues to hold.

Injuries and practice participation, snap/route participation, weather, expected pace and scoring environment, betting totals, offensive-line or quarterback changes, schedule-adjusted opponent strength, and the displayed outcome range are **Decision Context only**. They are shown to help the user make the final call but do not alter the Start/Sit ranking.
"""

DISCLAIMER_LANGUAGE = """
**Important limitations**

This is an informational fantasy-football decision aid, not a guarantee, medical assessment, official availability report, sportsbook projection, or betting product. Data feeds can be delayed, corrected, incomplete, or temporarily unavailable, and late inactive announcements may occur after the app's last refresh. Confirm official team/NFL game status and trusted breaking news before kickoff. Projections are estimates built from past and current-season observations; role changes, injuries, coaching decisions, weather and unusual game scripts can make actual results differ substantially. You remain responsible for the final lineup decision.
"""
