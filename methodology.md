# Modeling Methodology

This document records analytical decisions before the final 2025 test results are examined.

## Research question

Do rolling target share and rolling air-yard share predict a wide receiver's following-game PPR production better than their most recent fantasy score?

## Primary window hypothesis

The five-game rolling window is expected to offer the best balance between stability and responsiveness.

## Definition of a previous game

A previous game is a listed regular-season player appearance. A played game with zero targets remains in the history and contributes:

- `0` target share
- `0` air-yard share
- the player's recorded PPR total, usually zero unless they produced through rushing, returns, or another scoring category

Missed scheduled weeks are not inserted as zero-performance games.

## Formal experiment

The formal comparison requires five previous appearances from the **same season**. This means the primary five-game experiment begins with a receiver's sixth recorded appearance of that season.

This rule prevents prior-season roles, team changes, and offseason personnel changes from entering the clean window comparison.

## Data split

- 2021–2023: development and training
- 2024: validation and selection of final rules
- 2025: one final unseen test

The 2025 results should not influence feature definitions, filters, model selection, or thresholds.

## Early-season dashboard fallback

The practical dashboard will use the player's previous five career appearances when five current-season appearances are unavailable:

| Prediction point | History used |
|---|---|
| First appearance of new season | Last five appearances from previous season |
| Second appearance | Current appearance 1 + last four from previous season |
| Third appearance | Current appearances 1–2 + last three from previous season |
| Fourth appearance | Current appearances 1–3 + last two from previous season |
| Fifth appearance | Current appearances 1–4 + last one from previous season |
| Sixth appearance onward | Previous five current-season appearances |

## Confidence labels

- **Normal:** five prior appearances, all from the current season, and no team change since the previous appearance
- **Reduced:** five prior appearances are available, but the history crosses an offseason
- **Low:** fewer than five career appearances are available or the player changed teams since the previous appearance
- **Unavailable:** no prior NFL appearance is available

These labels communicate data limitations; they are not statistical prediction intervals.

## Leakage prevention

Every rolling metric is shifted by one appearance. The game being predicted never contributes to its own features. Rolling histories are calculated chronologically using stable player IDs rather than player names.
