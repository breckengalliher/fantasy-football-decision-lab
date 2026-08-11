# RealTime Fantasy Sports 2026 Market Source Audit

## Decision

Use the published RealTime Fantasy Sports average auction values as the
dashboard's default 2026 market benchmark. Keep the custom league model as the
primary valuation and label this source as an external comparison.

## Source profile

- Publisher: RealTime Fantasy Sports
- Publication: 2026 Average Fantasy Auction Value
- Coverage date: auctions through July 27, 2026
- Source type: observed average auction results
- Published entries: 148
- Included positions: QB, RB, WR, TE, K, and D/ST
- Published value range: $1.00–$64.22

The normalized dashboard file excludes no published rows. Kickers remain in the
source file for auditability but do not match the no-kicker model board.

## Compatibility findings

This is a current, behavior-based market benchmark and is therefore more useful
than converting rankings or ADP into synthetic dollars. The public sheet does
not specify one exact scoring and roster profile, however, so its values should
not be interpreted as league-specific fair value.

The application compares these observed prices with its own 12-team, full-PPR,
$200, six-point passing-touchdown league model. Exact normalized player names
are matched; unmatched players retain the internal baseline.

## Refresh procedure

Download the current PDF from the attributed source and run:

```bash
python src/extract_rtsports_aav.py INPUT.pdf data/external/rtsports_2026_aav.csv
```

The extractor validates the publication date, duplicate names, numeric values,
and recognized positions before replacing the reviewed CSV.
