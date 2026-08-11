# Dashboard Brief

## Product

**Fantasy Football Decision Lab**

An interactive 2026 fantasy-football dashboard that helps users identify auction
draft values, compare weekly start/sit options, and inspect the advanced metrics
behind each recommendation.

## Primary audiences

1. Fantasy-football managers making draft and lineup decisions
2. Recruiters and hiring managers evaluating an end-to-end analytics portfolio

## Primary decisions

- Which players should I target or avoid at their expected auction price?
- Which player should I start this week?
- What opportunity, efficiency, matchup, and uncertainty signals support the recommendation?

## Core workspaces

### Overview

Default landing page for portfolio reviewers and returning users.

Hero metrics:

- number of identified draft targets
- largest difference versus the labeled comparison source
- discretionary auction-value pool
- current data status

Primary outputs:

- best-value player
- strongest floor profile
- highest-risk player
- ranked custom league values and comparison differences
- position-level value summary
- links to the three decision workspaces

### Draft Target Finder

Hero metrics:

- league budget and discretionary value pool
- number of filtered draft targets
- highest available custom league value

Primary controls:

- position
- optional comparison-value ceiling
- minimum comparison difference
- confidence

Primary outputs:

- ranked auction-edge chart
- custom league value versus an optional labeled comparison
- floor, median, and ceiling projections
- draft signal and explanation
- complete filterable auction board

### Weekly Start / Sit

Hero metrics:

- recommended player
- median projected PPR
- matchup classification
- confidence

Primary controls:

- week
- lineup position
- two to four players for comparison

Primary outputs:

- projection comparison
- floor and ceiling
- matchup and injury context
- explanation of recommendation drivers

### Player Explorer

Hero metrics:

- projected season points
- auction value
- floor and ceiling
- confidence

Primary outputs:

- opportunity, efficiency, and risk profiles
- position-specific advanced metrics
- previous-five-game history
- role classification
- projection and optional comparison-source context

### Methodology

Shows:

- sources and refresh status
- feature and model definitions
- validation design
- final holdout results
- known limitations

## Delivery

- First surface: version-controlled Streamlit application
- Final target: publicly accessible deployment linked from GitHub and résumé
- Current milestone: interactive structure preview with clearly labeled illustrative data
