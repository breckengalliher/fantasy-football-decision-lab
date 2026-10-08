"""User-facing source attribution and responsible-use language."""

SOURCE_ATTRIBUTION = """
**Data sources**

- **Player results, schedules, snap counts, team play volume, game lines and schedule data:** [nflverse public data releases](https://github.com/nflverse/nflverse-data). nflverse republishes and standardizes NFL data; it is not affiliated with the NFL.
- **Injuries and practice participation:** [nflverse daily injury reports](https://github.com/nflverse/nflverse-data), with [Sleeper](https://docs.sleeper.com/) used only as a once-daily fallback or disagreement check. nflverse remains authoritative when both sources provide a designation.
- **Pregame weather, game totals and depth charts:** [SportsDataIO](https://sportsdata.io/), when the provider connection is available. The time shown in the app is when this app last retrieved the provider data—not a guarantee that every underlying report changed at that time.
- **Player-prop market expectations:** consensus player-prop lines from SportsDataIO's NFL props feed, when included in the connected subscription and offered by sportsbooks. Multiple available books are combined by median; missing or suspended markets are shown as unavailable, never as zero.
- **Narrative reporting context:** [ESPN's official NFL RSS feed](https://www.espn.com/espn/rss/nfl/news) and recent public posts returned by the [Bluesky public API](https://bsky.network/docs/category/http-reference/) from accounts whose profiles identify reporting or editorial work. Links are shown with each matched outlook. Reporting is summarized for context only and is never a model input.
- **Player roster photos:** current active-player identifiers from [Sleeper](https://docs.sleeper.com/), displayed from Sleeper's image CDN when a photo is available. Missing photos are left blank.
- **Model calculations and Start/Sit labels:** produced by this app from the credited source data. They are not rankings or projections supplied by nflverse, SportsDataIO, the NFL, ESPN, or the listed teams.

Missing provider data is labeled unavailable or not connected; it is never silently interpreted as healthy, active, or unchanged.
"""

METHODOLOGY_LANGUAGE = """
**What determines the Start/Sit label**

The app ranks only the players selected in the same comparison. “Start” means the highest median projection among those choices; “Sit” means a lower-ranked choice in that comparison. It is not a universal command to start or bench that player.

- **RB, WR and TE:** current-season PPR production is adjusted toward repeatable recent workload. Touchdowns are regressed toward position-level opportunity rates, prior-season production fades as the current-season sample grows, and the opponent adjustment is capped and scaled to the amount of evidence available.
- **QB:** the selected 4-point or 6-point passing-touchdown setting is applied throughout. Recent passing/rushing workload, regressed touchdown and turnover rates, a fading prior-season anchor, and a capped opponent adjustment form the median estimate. Only quarterbacks verified as QB1 by the connected depth-chart feed can enter the public comparison pool.
- **Newly promoted players:** a player with no usable current-season game sample may enter the comparison pool only when the live depth chart verifies a fantasy-relevant role (QB1, top-two RB, top-three WR, or top-two TE). We use a conservative current-season position/role baseline, display a wider range, and label the estimate **Limited sample** until real workload is recorded.
- **Ranges:** Floor, projection and ceiling are calibrated P10, median and P90 outcomes. They describe model uncertainty, not minimums or maximums; roughly 10% of outcomes may fall below the floor and 10% above the ceiling if calibration continues to hold.

The main ranking keeps injuries and practice participation as Decision Context and does not alter the baseline projection. When applicable, an optional **Injury-adjusted outlook** appears inside an individual player card. It applies a transparent availability/workload scenario from current game status, practice progression, quarterback availability, and partial teammate-opportunity redistribution. It never infers an exact medical return date. Weather, pace, game totals and journalism remain informational only.

When valid player props are available, **Market expectation** converts consensus receiving, rushing and passing lines to the selected fantasy scoring format. Touchdowns are probability-weighted and sportsbook margin is removed when both sides are available. Market expectations are supplemental only and never alter the calibrated projection, range or Start/Sit ranking.

Journalism and verified reporter commentary are also **narrative only**. They may be summarized in the Player Outlook to explain role expectations or uncertainty, but they never change the projection, outcome range, player ranking, or Start/Sit label.
"""

DISCLAIMER_LANGUAGE = """
**Important limitations**

This is an informational fantasy-football decision aid, not a guarantee, medical assessment, official availability report, sportsbook projection, or betting product. Data feeds can be delayed, corrected, incomplete, or temporarily unavailable, and late inactive announcements may occur after the app's last refresh. Confirm official team/NFL game status and trusted breaking news before kickoff. Projections are estimates built from past and current-season observations; role changes, injuries, coaching decisions, weather and unusual game scripts can make actual results differ substantially. You remain responsible for the final lineup decision.
"""
