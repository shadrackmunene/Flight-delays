# Analytical Questions and Hypotheses

**Main question.** How do airline reliability and flight delays vary across time, airlines, airports and routes,
and how accurately can historical schedule and operational information predict late arrivals?

Primary outcome: *late arrival* = `arr_delay >= 15` minutes, among completed flights. Cancellations and diversions
are analysed as separate outcomes. Hypotheses below were written after the descriptive scan (Stage 3) suggested
them and **before** the inferential work (Stage 4) and modelling (Stage 5); each states how it would be falsified.
Stage 4/5 will report which were supported, not supported, or inconclusive.

| ID | Question | Hypothesis | Method (stage) | Would be refuted if |
|---|---|---|---|---|
| H1 | Has reliability changed over 2009–2018? | No monotonic improvement or deterioration: year-to-year swings (e.g. 2014) dominate any trend, even after adjusting for month and airline mix. | Logistic/linear-probability model with year effects, month and carrier terms; cohort comparison (S4) | A year trend with a practically meaningful slope (> ~0.5 pp/yr) survives adjustment |
| H2 | Do airlines differ after accounting for where and when they fly? | Raw airline gaps shrink materially after adjusting for origin, destination, month and departure hour, but some persist. | Fixed-effects regression / mixed model; adjusted vs unadjusted gaps (S4) | Adjusted gaps ≈ raw gaps (no mix effect) or ≈ 0 (all raw gap was mix) |
| H3 | Which airports and routes are persistently poor? | Persistent poor performance exceeds what independent year-to-year luck would produce, and is concentrated in the NYC area, Chicago, SFO and a few long-haul hubs. | Observed vs binomial-chance persistence counts; shrinkage-based ranking (S3/S4) | Observed counts match the chance expectation |
| H4 | Is delay risk driven by time of day? | Late-arrival risk rises through the day (delay propagation) and the hour effect persists after adjusting for airline and airport. | Hour effect in adjusted models (S4) | Hour coefficients vanish after adjustment |
| H5 | Does departure delay carry through to arrival? | Most departure delay is not recovered in flight: median recovery is a few minutes, regardless of delay size. | Descriptive + regression of arr_delay on dep_delay (S3/S4) | Large delays are recovered at a materially higher rate |
| H6 | Is long taxi-out an early warning beyond departure delay? | Taxi-out adds predictive information about late arrival even for flights that left on time (part mechanical, not causal). | Model B vs a model with departure delay only (S5) | Taxi-out adds no held-out improvement |
| H7 | What causes cancellations? | Weather is the largest cause and is seasonal (winter); carrier-caused cancellations vary by airline and year. | Counts and rates by code/month/carrier (S3) | Weather is not the leading cause |
| H8 | Are conclusions sensitive to the 15-minute definition? | Airline and airport rankings are stable across 0/15/30/60-minute thresholds; absolute rates are not. | Rank correlation across thresholds (S4) | Rankings change substantially across thresholds |
| H9 | Can flights be predicted before departure? | Pre-departure information (Model A) provides only a modest improvement over a historical-rate baseline; post-departure information (Model B) improves discrimination substantially. | Chronological hold-out; PR-AUC vs baseline (S5) | Model A ≈ Model B, or Model A ≈ baseline |
| H10 | Is model performance stable over time and groups? | Performance degrades somewhat on later periods and differs across airlines/airports. | Test-period slices (S5) | Metrics are flat across slices |

## Data limitations that shape the design

- Oct 2009 and Jul 2011 are absent; Jun 2011 and Sep 2009 appear twice (duplicates removed). Trend work uses matched months
  (all months except Jul and Oct) or compares like with like.
- Carrier reporting is irregular (for example 9E, MQ and OH disappear for several years; six regional carriers appear in 2018),
  so trend work also uses the 10 carriers that report in every year.
- No weather, aircraft, crew or air-traffic-control data. Causal interpretation of any association is not possible.
