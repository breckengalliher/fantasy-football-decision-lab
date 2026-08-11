# Project Checkpoint — July 23, 2026

## Goal

Build a GitHub- and résumé-ready fantasy football application for 2026 draft
targets and weekly lineup decisions.

## League settings

- 12 teams
- Full PPR
- $200 auction budget per team
- 1 QB, 2 RB, 2 WR, 1 TE, 2 FLEX, 1 D/ST
- 6 bench spots and no kicker
- Six points per passing touchdown
- ESPN-style D/ST scoring without yards-allowed scoring

## Completed

- Reproducible nflverse historical-statistics pipeline
- 2021–2025 WR research and time-aware validation notebooks
- Weighted 2023–2025 player model for 2026 estimates
- Verified 2026 nflverse roster integration
- Week 1 schedule and opponent integration
- League-specific replacement-level auction-value engine
- Exact $2,400 allocation across 180 projected draft selections
- Current 933-entry draft board
- Actual recent-game histories for rostered players
- Streamlit application with:
  - Overview
  - Draft Target Finder
  - Weekly Start / Sit
  - Player Explorer
  - Methodology
- Optional reviewed market-value CSV upload
- 2023–2025 weighted D/ST projection and auction-value model
- Current 2026 offensive depth-chart integration
- Executed 2026 roster-pipeline audit
- 17 passing automated tests
- Current RealTime Fantasy Sports average auction benchmark
- 148 reviewed market rows with 132 exact draft-board matches
- Reproducible PDF-to-CSV market extractor and source audit
- Injury-source quality assessment and explicit unavailable-data safeguards

## Current limitations

- The current market benchmark reflects observed public auction results but is
  not calibrated to one exact league configuration.
- Players without qualifying historical production remain visible with an
  unavailable projection and $1 placeholder.
- Injuries, consensus projections, and defensive matchup strength
  are not connected yet.

## Resume point

Connect current injury context, add consensus projection/ADP comparisons,
complete visual polish, publish the repository to GitHub, and deploy the
application.
