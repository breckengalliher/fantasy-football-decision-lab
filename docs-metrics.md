# Wide Receiver Metric Dictionary

This document explains each statistic in plain language. We will only promote a metric into the final analysis after verifying that the required source fields are available and reliable.

## Outcome metric

### PPR fantasy points

**Formula:** `receptions + 0.1 × receiving yards + 6 × receiving touchdowns`

**Meaning:** The fantasy result we ultimately want to understand or predict.

**Caution:** Touchdowns are valuable but relatively rare, so one touchdown can make a low-volume week appear stronger than the underlying role.

## Opportunity metrics

### Targets

The number of passes directed at a receiver. Targets are usually more repeatable than touchdowns and are a simple measure of involvement.

### Target share

**Formula:** `player targets ÷ team pass attempts` or, depending on source convention, `player targets ÷ team targets`.

This measures how much of the passing offense flows through the receiver. We must state and consistently apply one denominator.

### Air yards

The total distance the ball travels toward a receiver on targets, measured from the line of scrimmage to the target location. Air yards describe intended opportunity, not completed production.

### Air-yard share

**Formula:** `player air yards ÷ team air yards`

This combines involvement and downfield role. A high share may signal valuable opportunity even when recent catches are low.

### Weighted opportunity

A future engineered metric that combines targets, air yards, and high-value red-zone usage. The weights must be learned only from training data to prevent leakage.

## Role metrics

### Average depth of target (aDOT)

**Formula:** `air yards ÷ targets`

Higher values indicate a deeper role. Deep targets have more yardage and touchdown upside but are generally less likely to be completed.

### Route participation and targets per route run

These are valuable role metrics, but route-level coverage varies by source and season. They remain optional until the data audit confirms reliable participation fields.

## Efficiency metrics

### Catch rate

**Formula:** `receptions ÷ targets`

Catch rate reflects results but is influenced by target depth, quarterback accuracy, and defensive coverage. It should not be interpreted as receiver skill alone.

### Yards per target

**Formula:** `receiving yards ÷ targets`

This measures production per opportunity. It can be noisy over small samples.

### Fantasy points per target

**Formula:** `PPR fantasy points ÷ targets`

This summarizes fantasy efficiency but can spike because of touchdowns. It is descriptive, not automatically predictive.

## Stability and predictive features

### Rolling average

The average of a metric across a player's previous games. For a Week 8 prediction, the calculation may use Weeks 5–7 but must never use Week 8 information.

### Rolling standard deviation

A measure of week-to-week volatility. A lower value suggests a steadier role or outcome.

### Fantasy points over expected

**Formula:** `actual fantasy points − expected fantasy points`

Positive values indicate production above what the opportunity model expected. This can represent skill, favorable circumstances, or short-term luck; it does not prove which explanation is correct.

## Core analytical rule

Every predictive feature must be available **before** the game being predicted. This prevents data leakage and makes the evaluation resemble a real weekly fantasy decision.
