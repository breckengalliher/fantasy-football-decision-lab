# 2026 Injury Source Assessment

## Decision

Do not adjust projections or recommendations from a partial injury source.
Display injury coverage as unavailable until a reviewed, refreshable feed is
connected.

## Intended use and grain

The application needs one current record per rostered player, including injury
or body-part detail, practice participation, game designation, source timestamp,
and expected return when available. The data must refresh often enough for
weekly lineup decisions and must distinguish an explicitly active player from a
player with no record.

## Sources reviewed

- nflverse: authoritative for the rest of this project's open data, but its
  injury source ended after the 2024 season and it reports no ETA for a
  replacement.
- Official NFL transactions: useful for reserve-list moves, but not a complete
  player injury or practice-status feed.
- Public fantasy injury pages: current narrative context exists, but complete
  structured coverage is subscription- or API-key-dependent.
- News search: useful for investigation, but too selective and unstable to
  classify unmentioned players as healthy.

## Quality finding

**High severity, high confidence:** no reviewed public source currently meets
the required completeness, grain, and refresh criteria. Joining a partial list
would create false negatives: missing players could appear healthy even though
the source simply omitted them.

## Safeguard implemented

Every dashboard player now receives:

- `injury_status = Unavailable`
- `injury_detail = No reviewed 2026 injury feed`
- an empty `injury_as_of`

The dashboard states that confidence and risk scores exclude current injuries.
An automated test prevents the missing feed from being represented as healthy.

## Connection contract for a future feed

Before activation, require:

1. A stable player identifier or audited name-to-ID mapping.
2. Unique current records at player grain after deterministic latest-record
   selection.
3. A source timestamp and a documented freshness threshold.
4. Controlled status values with unknown values preserved, not coerced active.
5. Join-coverage reporting and duplicate-key rejection.
6. A fallback that visibly marks stale or failed refreshes as unavailable.
