# 2026 Auction Value Methodology

## League configuration

- 12 teams
- $200 budget per team
- $2,400 total league spending
- Full PPR
- Six points per passing touchdown
- Starters: 1 QB, 2 RB, 2 WR, 1 TE, 2 RB/WR/TE FLEX, and 1 team defense
- Six bench slots
- No kickers
- Minimum player bid: $1

## Team-defense scoring

- Sack: 1
- Interception: 2
- Fumble recovery: 2
- Blocked punt, PAT, or field goal: 2
- Safety: 2
- D/ST touchdown: 6
- Points allowed: 5 for 0; 4 for 1–6; 3 for 7–13; 1 for 14–17;
  0 for 18–27; -1 for 28–34; -3 for 35–45; and -5 for 46+
- Yards allowed: not scored

Following ESPN's D/ST convention, points scored by an opposing interception or
fumble return touchdown do not count against the defense's points-allowed
total.

The machine-readable configuration is stored in [`config/league.json`](config/league.json).

## Why roster settings affect dollar values

Auction values are league-specific. This format produces 15 roster slots per
team and 180 purchases across the league. At a $1 minimum bid:

```text
minimum-bid reserve = 180 players × $1 = $180
discretionary dollars = $2,400 − $180 = $2,220
```

These settings change:

- the number of draftable players
- the replacement level at every position
- the number of dollars available for premium players
- the value of positional scarcity

## Implemented valuation process

### 1. Produce 2026 fantasy-point projections

Each position will use position-appropriate features:

- **QB:** passing volume, touchdown rate, rushing production, pressure and
  efficiency measures
- **RB:** carries, targets, route involvement, goal-line work, yards after
  contact proxies, and team opportunity share
- **WR:** targets, target share, air-yard share, role, efficiency, and recent
  usage
- **TE:** routes, targets, target share, red-zone usage, and position-relative
  efficiency
- **DST:** sacks, takeaways, touchdowns, points allowed, opponent strength,
  quarterback pressure, and implied game environment

### 2. Define the projected 180-player draft pool

The current roster-demand assumptions are:

- 24 quarterbacks
- 54 running backs
- 66 wide receivers
- 24 tight ends
- 12 team defenses

This produces exactly 168 offensive selections plus 12 defenses. Replacement
level is the projected point total at the final selected slot for each
offensive position. These assumptions are stored in `config/league.json` and
can be revised when league draft-history data becomes available.

### 3. Calculate value over replacement

```text
VORP = projected fantasy points − positional replacement-level points
```

Players outside the projected draft pool receive a recommended value of $0.
This means "do not plan to spend a draft dollar," not that the platform permits
a $0 winning bid.

### 4. Reserve minimum bids

Every drafted roster slot requires at least $1. The locked minimum-bid reserve is:

```text
minimum reserve = 180 drafted slots × $1 = $180
```

### 5. Allocate every remaining auction dollar

```text
discretionary dollars = $2,400 − $180 = $2,220

defense allocation = $34
offensive base bids = 168 × $1 = $168
offensive VORP pool = $2,400 − $34 − $168 = $2,198

offensive player premium =
    player positive VORP ÷ total positive offensive VORP
    × $2,198
```

The engine floors each calculated premium and distributes remaining dollars in
descending order of fractional remainder. This largest-remainder method makes
the 180 draftable values reconcile exactly to $2,400 after integer rounding.

Defense prices are intentionally conservative: $5 for D/ST 1, $4 for D/ST
2–3, $3 for D/ST 4–6, $2 for D/ST 7–12, and $0 for the remaining defenses.

### 6. Add uncertainty and market context

The dashboard separates:

- **Custom league value:** the primary value derived only from this league's
  projections, scoring, roster demand, replacement levels, and budget
- **Comparison value:** an optional external 2026 price or clearly labeled
  internal historical baseline

External prices never determine the custom league value. When a reviewed 2026
market file is available, the comparison difference is:

```text
comparison difference = custom league value − external market value
```

Without an uploaded 2026 market source, the dashboard compares against a
separately labeled 2025-production baseline and must not call it market price.

## Dashboard outputs

Each player should receive:

- projected 2026 fantasy points
- positional rank and overall rank
- replacement-level baseline
- value over replacement
- custom league auction value
- optional comparison value and its source
- comparison difference
- floor, median, and ceiling projection
- confidence label
- key opportunity and efficiency statistics
- short explanation of the value signal

## Limitations

Auction values are recommendations, not objective prices. Actual values depend
on nomination order, remaining budgets, roster construction, league behavior,
injury news, depth-chart changes, and how aggressively managers concentrate
spending among elite players.
