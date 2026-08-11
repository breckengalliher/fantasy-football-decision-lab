# ESPN 2026 Market Source Audit

## Controlling source

- ESPN 2026 Fantasy Football Draft Kit, PPR Top 300
- Last updated August 9, 2026
- Published format: 10 teams, $200 per team, full PPR
- Published roster: 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 1 K, 1 D/ST, 7 bench
- Published quarterback scoring: four points per passing touchdown

## Portfolio conversion

The portfolio league uses 12 teams, $200 per team, two FLEX starters, no
kicker, six bench spots, and six points per passing touchdown. ESPN does not
publish a directly equivalent static sheet. The dashboard therefore treats
ESPN as a market benchmark, not as the custom fair-value model.

The conversion selects the 168 highest-ranked offensive players and the top 12
defenses, assigns a $1 minimum bid to each of the 180 draft-pool entries, and
allocates the remaining $2,220 in proportion to ESPN's published 10-team dollar
values. The resulting comparison pool totals exactly $2,400. Kickers are
excluded. Players without an exact normalized-name match are labeled as missing
rather than assigned an inferred ESPN value.

## Known limitation

The calibration preserves ESPN's relative prices but does not reconstruct
ESPN's proprietary custom-value generator. In particular, ESPN's source prices
reflect four-point passing touchdowns. The portfolio's independent model remains
the decision value because it uses the actual six-point passing-touchdown rule.

