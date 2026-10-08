# Player Trends redesign and mobile implementation plan

Date: 2026-10-08

## Five largest weaknesses in the previous experience

1. The production view behaved like a one-week scoreboard, so users could not understand season shape, rolling form, volatility, or missing weeks at a glance.
2. The player header omitted the projection range and gave availability the same visual weight whether action was required or not.
3. Opportunity, sustainability, and next-action reasoning were scattered across tabs instead of answering the manager's decision questions immediately.
4. There was no full-season/last-five/last-three control, optional reference lines, detailed tooltip context, or compact weekly game log.
5. Mobile inherited the desktop information order. It was responsive, but not intentionally prioritized around a compact identity, key metrics, touch-friendly chart, concise insights, and expandable evidence.

## Redesigned desktop experience

The page now follows an answer-first hierarchy:

1. Position and searchable player selection.
2. Compact player overview with team, opponent, kickoff, availability, projection, recent PPR, season PPR, and projected floor-to-ceiling range.
3. Three evidence-based manager insights: role trajectory, sustainability, and what to watch next.
4. One Analysis panel containing Production, Opportunity, Matchup, and Player Profile views.
5. Expandable weekly game log and sources.

The Production view is now an interactive SVG chart rather than a week-at-a-time scoreboard. It separates completed results from the upcoming projection, displays the calibrated projection range, supports season/last-five/last-three periods, and allows season and recent averages to be toggled independently. Missing weeks are rendered as gaps and are not connected as played games.

## Redesigned mobile-web experience

The mobile layout is intentionally vertical:

1. Compact player identity and action-needed availability badge.
2. A two-by-two key-metric grid.
3. Three concise insight cards.
4. Touch-sized analysis tabs.
5. A full-width chart with touch tooltips and large period controls.
6. Expandable weekly game log rather than a horizontally scrolling table.

No page-level horizontal overflow is required. Desktop and mobile use the same metric definitions, calculations, and projection data.

## Implemented analytics

- Full-season, last-five-week, and last-three-week production views.
- Season and recent-average reference lines.
- Weekly PPR with quarterback scoring-format adjustment.
- Floor, median, and ceiling shown separately from completed results.
- Opportunity trend based on attempts plus carries for QBs, carries plus targets for RBs, and targets for WRs/TEs.
- Opportunity expansion/contraction based on the recent sample versus the player's season workload.
- Conservative touchdown-led scoring warning when production rises without comparable opportunity growth.
- Matchup and availability watch items using existing validated fields.
- Compact weekly game log using only recorded fields.

Not implemented because the current validated dataset does not support them consistently:

- Expected fantasy points.
- Weekly routes and route participation.
- Weekly snap share.
- Weekly red-zone and goal-line opportunity.
- Position-relative percentile ranks.

These metrics should not appear until their sources, definitions, missing-data behavior, and refresh process are validated.

## Performance impact

- The chart uses lightweight inline SVG, CSS, and a small self-contained script.
- No plotting library, API request, or new dependency was added.
- The chart receives only the selected player's completed-season rows.
- Time-period and reference-line changes happen in the browser without a Streamlit rerun.
- Local Player Trends navigation measured approximately 298 ms after the shared snapshot was loaded.
- Initial local application run measured approximately 2.20 seconds in the same validation pass.

## Validation

- 111 automated tests pass.
- Python compilation and whitespace checks pass.
- QB, RB, WR, and TE player pools render without exceptions.
- Production, Opportunity, Matchup, and Player Profile views render without exceptions.
- Missing weeks remain explicit gaps in the production data passed to the chart.
- Four-point and six-point quarterback weekly results use the selected scoring format.
- Desktop and mobile layouts were visually inspected in the local preview.

## Native mobile implementation plan

No native iOS, Android, Flutter, React Native, or Expo application currently exists in this repository. The recommended future implementation is a shared API plus native presentation components; the projection engine should remain in Python.

### Shared API contracts

- `GET /players?position=`: searchable roster-relevant player summaries.
- `GET /players/{id}/trends?period=season|5|3&scoring=`: player header, weekly production, opportunity fields, projection range, and insights.
- `GET /players/{id}/matchup`: validated matchup and freshness context.

All responses should include schema version, scoring format, data timestamp, missing-value reasons, and metric-definition identifiers.

### Reusable native components

1. `PlayerSearchHeader`
2. `PlayerOverviewCard`
3. `KeyMetricGrid`
4. `WeeklyPerformanceChart`
5. `PeriodSegmentControl`
6. `TrendInsightCard`
7. `OpportunityMetricPanel`
8. `MatchupEvidencePanel`
9. `WeeklyGameLog`
10. `DataFreshnessFooter`

### Mobile behavior

- Swift Charts on iOS and Compose Charts or the selected Android chart system should receive the same normalized weekly series.
- Null weeks must break line segments.
- Tooltips should open on tap and drag, not hover.
- The chart period and reference-line preferences should be local UI state and must not trigger a projection refresh.
- Accessibility labels must announce week, opponent, actual PPR, or projection range in one sentence.
- Metric names and insight classifications should be sourced from shared definitions rather than recreated separately in each client.

## Recommended next features

| Priority | Feature | User value | Effort |
|---|---|---:|---:|
| 1 | Validated weekly snap and route participation history | Very high | Medium |
| 2 | Expected fantasy points from documented opportunity inputs | Very high | High |
| 3 | Saved players and watchlist trend alerts | High | Medium |
| 4 | Position-relative percentile context | High | Medium |
| 5 | Shareable Player Trends image/link | Medium | Low |
| 6 | Multi-player trend overlay | Medium | Medium |

