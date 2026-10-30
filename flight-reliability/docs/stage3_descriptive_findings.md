# Stage 3: Descriptive Findings

All numbers are read from `reports/tables/*.csv`, produced by `python -m flightrel.descriptive` from the cleaned data
(60.5M flights with `analysis_include = TRUE`). Figures are in `reports/figures/`. These are **descriptive and
unadjusted**; inference and adjustment follow in Stage 4.

**Definitions.** Late arrival = `arr_delay >= 15`, over completed flights with a known arrival delay. Cancellation rate =
cancelled / scheduled flights. "Matched months" excludes July and October in every year, because Oct 2009 and Jul 2011
are absent. "Stable carriers" are the 10 carriers reporting ≥ 10,000 flights in every year (AA, AS, B6, DL, EV, F9, HA, OO, UA, WN).
Negative delays are kept in every median and percentile.

## A. Annual trends (fig 01)

| | Lowest | Highest |
|---|---|---|
| Late-arrival rate, matched months | 16.2% (2012) | 22.0% (2014) |
| Late-arrival rate, 10 stable carriers | 16.9% (2012, 2016) | 22.1% (2014) |
| Cancellation rate, matched months | 1.1% (2012, 2016) | 2.4% (2014) |

- **No monotonic trend.** The rate moves up and down: 18.7% (2009) → 16.2% (2012) → 22.0% (2014) → 17.2% (2016) → 19.0% (2018).
- **Composition does not drive the picture.** The all-data, matched-month and stable-carrier series agree to within 0.9 percentage
  points in every year (largest gap 0.84 pp, all-data vs stable carriers in 2009), so the year-to-year pattern is not an artefact of the missing months or the 2018 carrier additions.
- The median arrival is early in every year and the median moved from −4 min (2009–2011) to −6 min (2016–2018) while the late
  *rate* did not improve. This is consistent with schedules becoming longer, but that was not tested here.

## B. Month, weekday and hour (figs 02–03)

- **Month (all years):** June 22.6% and July 22.5% late, December 22.1%; lowest November 14.8%, September 14.8% and October 15.4%.
  Cancellations peak in February (3.0%) and January (2.8%) and are lowest in November (0.8%).
- **Weekday (matched months):** Thursday and Friday worst (20.5% each), Saturday best (16.2%), Tuesday 17.8%.
- **Scheduled departure hour (matched months):** risk rises almost monotonically through the day, from 7.8% at 05:00 and 9.2% at
  06:00 to 26.3% at 20:00 (about 2.9 times the 06:00 rate), then falls after 21:00. Departure-delay rates follow the same shape
  (5.6% at 05:00, 27.3% at 20:00). Hours 00:00–04:00 carry under 100,000 flights each and are not plotted.

## C. Airlines (figs 04–05) — unadjusted

- Matched months, all years: lowest HA 8.8%, AS 13.8%, DL 15.1%; highest OH 23.9%, B6 23.8%, F9 23.3%, NK 22.8%, EV 22.0%.
  The largest carrier, WN, is at 19.3%. Intervals are very narrow (e.g. WN 19.31–19.36%, n = 9.9M), so the gaps between most
  carriers are statistically clear, but statistical clarity is not the same as a like-for-like comparison.
- **These comparisons are confounded.** Carriers fly different routes and airports, and several appear in only some years
  (NW 2009 only, CO 2009–2011, YX 2018 only). Stage 4 adjusts for route/airport/time mix.
- **Stable carriers move a lot over time** (fig 05): DL fell from 20.0% (2009) to 13.9% (2018); B6 rose from 21.3% to 27.6%;
  F9 from 20.1% to 28.1%; AS was 11.5–13.2% in 2010–2016 and 17.2% and 16.3% in 2017–2018. Rankings are therefore only partly stable.

## D. Airports and routes (figs 06–07)

- **Origins with the highest late-arrival rates:** EWR 24.7%, ORD 24.1%, SFO 22.6%, MDW 22.3%, JFK 22.2%, DFW 22.2%.
  Lowest: ITO 8.1%, LIH 9.6%, KOA 9.8%, HNL 10.5%, OGG 10.9%. By destination: EWR 27.7%, SFO 26.3%, LGA 24.6%.
  The busiest airport (ATL, 3.2M completed flights) is mid-pack at 17.8% (rank 57 of 111), so size alone does not explain the ranking.
- **Persistence beyond luck (airports).** Of 105 airports observed in ≥ 8 years, 61 were in the worst quartile of airports in at
  least one year, but 16 were in it in 6 or more years, against about 2 expected if each year were an independent draw.
  EWR, ORD and DFW were in the worst quartile in all 10 years.
- **Persistence (routes).** Of 2,786 routes (≥ 300 completed flights in ≥ 8 years), 103 were in the worst decile in 6 or more years,
  against about 0.4 expected by chance. Routes poor in all 10 years include IAD–EWR (33.7% late), EWR–RIC (33.3%), SMF–SFO
  (32.3%), ORD–EWR (31.4%), MDW–LGA (30.6%) and DEN–SFO (28.8%); many involve EWR, LGA, SFO or ORD.
- Caveat: the chance model assumes independent years with equal probability, so it shows persistence is real but not why;
  the screening of 2,786 routes also means some individual route labels will be false positives.

## E. Departure delay and arrival delay (fig 08)

- Correlation between departure and arrival delay: **0.94** across 49.9M completed flights.
- Share arriving late by departure delay: under −5 min 2.4%; −5 to −1 min 3.6%; 0–14 min 10.5%; 15–29 min 52.3%; 30–59 min 94.2%;
  60 min or more ≈ 100%.
- Of 8.98M flights that departed 15 or more minutes late, **19.9%** still arrived within 15 minutes of schedule (3.3% arrived early).
- Median gate-to-gate recovery is only 5–6 minutes at every level of departure delay (the mean recovery shrinks from about 4.5 min
  for on-time departures to 2.5 min for delays over two hours). Late departures are therefore mostly carried to arrival, not absorbed.

## F. Taxi times (fig 09)

- Among flights that **left on time** (< 15 min), the late-arrival rate rises from 1.4% (taxi-out under 10 min) to 3.6% (15–19 min),
  8.1% (20–29), 27.4% (30–44) and 76.9% (45+). Among late departures it rises from 72% to 99%.
- Across the 77 airports with ≥ 100,000 departures, median taxi-out correlates 0.51 with the airport late rate. LGA and JFK have a
  median taxi-out of 23 minutes, EWR 19, versus 8–9 at OGG, ONT and HOU.
- Taxi-in (known only after landing): 38.3% late when taxi-in is 20+ min versus 17.3% under 5 min. This is not usable as a predictor.
- Taxi time is part of gate-to-gate time, so part of these associations is arithmetic and not a causal effect.

## G. Cancellations (fig 10)

- Of cancelled flights with a reason code (all years): weather 49.2%, carrier 32.1%, national air system 18.6%, security 0.1%.
- Weather cancellations are concentrated in winter (January 84.9k, February 94.2k, December 57.4k flights) and peaked in 2018
  (62.0k) and 2014 (61.2k). Carrier-coded cancellations ranged from 18.6k (2017) to 42.2k (2010).
- Highest carrier cancellation rates (matched months): OH 4.2%, MQ 3.7%, YX 3.3%, EV 3.0%; lowest HA 0.2%. These carriers are
  mostly regional; their years of coverage differ, so this is also unadjusted.

## What these results do and do not support

*Measured:* the patterns above, with sample sizes and 95% Wilson intervals in the tables.
*Not established:* why any pattern exists (no weather, aircraft, crew or air-traffic data), whether carrier gaps survive adjustment for
route and airport mix, and whether any of it is causal. Those questions are addressed, as far as the data allows, in Stages 4–5.
